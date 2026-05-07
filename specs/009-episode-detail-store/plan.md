# Implementation Plan: PPO Episode Detail Store

**Branch**: `009-episode-detail-store` | **Date**: 2026-05-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/009-episode-detail-store/spec.md`

## Summary

把 PPO OOS evaluator 的完整 trajectory（含 reward 拆解、action vector、SMC overlay、per-asset OHLC）持久化成 **單檔 episode artefact**，由 005 Inference Service 在啟動時 eager load 進記憶體，透過新增的 `GET /api/v1/episodes` 與 `GET /api/v1/episodes/{id}` 兩個 read-only endpoint 暴露；006 Spring Gateway 1:1 反向代理；007 戰情室 Overview 直接消費真實 OOS 資料。policy 不重訓、env / reward function / 資料快照不動，整個 feature 只擴 evaluator 輸出 + 新增 artefact builder + 新增兩個 read endpoint。

## Technical Context

**Language/Version**:
- Python 3.11（evaluator + artefact builder + 005 service；對齊既有 `pyproject.toml` 與 dev container）
- Java 25 LTS + Spring Boot 4.x（006 gateway；對齊 constitution Technology Stack）
- TypeScript 5.x + React 18（007 warroom；既有專案）

**Primary Dependencies**:
- Python：`pyarrow`（trajectory.parquet）、`numpy`、`pandas`（既有）；`stable-baselines3`（既有，evaluator load）
- 005：`fastapi`、`pydantic v2`、`uvicorn`、`apscheduler`、`redis.asyncio`（皆既有）
- 006：`spring-boot-starter-webflux`（既有）；`okhttp` for tests（既有）
- 007：`@tanstack/react-query`、`zod`（既有）

**Storage**:
- Episode artefact：**單一 JSON 檔** `episode_detail.json`（≈ 5 MB；329 frames × 6 assets OHLC + reward + action + smc + 6 SMC overlays）
- 隨 005 Docker image build 時透過 `COPY` 打包進 `/app/episode_detail.json`
- 不引入資料庫；inference service lifespan 啟動時讀檔 → 記憶體 dict
- Trajectory parquet 落在 `runs/<run_id>/eval_oos/trajectory.parquet`（artefact builder 的中間產物）

**Testing**:
- Python unit / integration / contract：pytest（既有 marker：`-m unit|integration|contract`）
- Java：JUnit 5 + Spring `WebTestClient` + WireMock（既有）
- Frontend：Vitest + Testing Library + zod schema fixtures（既有）

**Target Platform**: Linux container（Docker compose, Zeabur 部署）；前端 evergreen browser
**Project Type**: 多服務 monorepo（已存在 `src/`、`services/gateway/`、`apps/warroom/`）
**Performance Goals**:
- 005 啟動 → endpoint ready ≤ 30 秒（含 episode artefact load + policy warmup）
- `GET /api/v1/episodes/{id}` 回應 ≤ 500 ms（artefact 已在記憶體；只是 dict 序列化）
- Overview 頁首屏 ≤ 5 秒（SC-001）

**Constraints**:
- artefact 體積 ≤ 10 MB（避免拖慢 image build；329 frames × ≈ 100 fields ≈ 5 MB JSON 估算）
- 不允許資料庫；不允許動態 episode 上傳；MVP 只有一個 OOS episode
- byte-identical reproducibility（Principle I）—— 同一 policy + 同一資料快照 → JSON 數值欄位完全相同
- 不可改 PPO env / observation shape / reward function（屬 003-ppo-training-env / 008-smc-engine-v2 範圍）

**Scale/Scope**:
- 1 個 episode（OOS run）；329 frames；6 assets；< 1 MB SMC overlay 總和
- 估計 LOC 變更：evaluator +200、artefact builder +250、005 endpoints +180、006 controller +120、frontend mapper 修補 +50

## Constitution Check

> 對齊 `.specify/memory/constitution.md` v1.1.0（2026-04-29 ratified）。三 NON-NEGOTIABLE 原則必須通過 gate；其餘原則記錄合規狀態。

| # | 原則 | 狀態 | 說明 |
|---|---|---|---|
| **I** | **Reproducibility（NON-NEGOTIABLE）** | ✅ PASS | (a) evaluator 已 fix seed（既有 `--seed 42`，env reset seed 影響 deterministic 內亂源）。(b) artefact builder 為純函數：相同 trajectory.parquet + 相同 OHLC parquet → 相同 JSON 內容；JSON 序列化使用 `json.dumps(..., sort_keys=True, separators=(",", ":"))` 保證 byte-identical。(c) 003 OOS 資料快照已固定（`data/raw/*.parquet`，feature 002 committed）。(d) **驗收**：跑兩次 `python -m ppo_training.evaluate ... && python scripts/build_episode_artifact.py`，比對兩份 episode_detail.json 的 sha256 必須相同（contract test T-CT-001）。 |
| **II** | Explainability | ✅ PASS | (a) reward 四元拆解、SMC signals 五元、SMC overlay 全部以結構化欄位輸出，前端 Overview 頁可直接視覺化（K 線+SMC、reward sidebar）。(b) artefact builder 與前端共用 008-smc-engine-v2 的 `batch_compute_events`，避免規則漂移。(c) 不引入「黑箱中介數值」；action raw / normalized / log_prob / entropy 全部開放。 |
| **III** | **Risk-First Reward（NON-NEGOTIABLE）** | ✅ PASS | (a) 本 feature **不**修改 reward function（reward shaping 屬 003 範圍）。(b) artefact 輸出的 reward 拆解必須含 returnComponent / drawdownPenalty / costPenalty 三項，不允許簡化為 single scalar；schema 強制三項都出現。(c) Invariant 檢查：每 frame `total ≈ return - drawdown - cost`（1e-9 容差）由 artefact builder 在組裝時驗證；違反則 fail fast。 |
| **IV** | Service Decoupling | ✅ PASS | (a) 005 ↔ 006 ↔ 007 仍走 HTTP/REST，無共享 DB / 共享記憶體。(b) episode artefact 是 **唯讀檔案**，僅 build-time 複製進 image，不是跨 service 共享 volume。(c) 每個 service 仍可在隔離容器啟動（005 帶 artefact 跑可獨立 curl 驗證；006 用 WireMock stub 005；007 用 vitest fixture）。 |
| **V** | **Spec-First（NON-NEGOTIABLE）** | ✅ PASS | (a) `specs/009-episode-detail-store/spec.md` 已通過 quality checklist 全綠。(b) 兩個 endpoint 的行為由 FR-013 / FR-014 / FR-016 定義；契約檔 `contracts/openapi-episodes.yaml` 為 implementation 唯一依據。(c) 任何「實作時臨時加 endpoint」MUST 先回 spec 補 FR；本 feature 不在 spec 外加 endpoint（只 GET 兩個，禁止 POST/PUT/DELETE）。 |

**Gate verdict**: ✅ All NON-NEGOTIABLE 通過；無 violation；`Complexity Tracking` 留空。

## Project Structure

### Documentation (this feature)

```text
specs/009-episode-detail-store/
├── plan.md                          # 本檔案
├── research.md                       # Phase 0：trajectory.parquet schema / artefact 序列化策略 / 005 lifespan
├── data-model.md                     # Phase 1：8 個核心 entity（spec Key Entities 的完整 schema）
├── contracts/
│   └── openapi-episodes.yaml         # /api/v1/episodes + /api/v1/episodes/{id} OpenAPI 3.1
├── quickstart.md                     # Phase 1：本機 e2e（evaluator → builder → compose up → curl）
├── checklists/
│   └── requirements.md               # specify 階段已完成
└── tasks.md                          # /speckit.tasks 產出
```

### Source Code (repository root)

```text
# Python AI 引擎（共用）
src/
├── ppo_training/
│   └── evaluate.py                   # ✏ 擴充：trajectory.parquet 多欄位輸出
├── inference_service/                # ✏ 擴充：episodes endpoints
│   ├── app.py                        #    新增 /api/v1/episodes + /{id} 路由
│   ├── episodes.py                   # 🆕 EpisodeStore（lifespan 載入、in-memory dict）
│   └── schemas.py                    #    +EpisodeSummaryDto / EpisodeDetailDto
└── smc_features/
    └── batch.py                      # 既有，read-only 引用

scripts/
└── build_episode_artifact.py         # 🆕 trajectory + summary + smc + ohlc → episode_detail.json

# Java Gateway
services/gateway/src/main/java/com/dayitw/warroom/gateway/
├── controller/
│   └── EpisodeController.java        # 🆕 GET /api/v1/episodes + /{id} proxy
├── dto/
│   ├── EpisodeSummaryDto.java        # 🆕
│   └── EpisodeDetailDto.java         # 🆕（含 trajectory / reward / smc / ohlc 巢狀）
└── service/
    └── EpisodeClient.java            # 🆕 WebClient 呼叫 005

services/gateway/src/test/java/com/dayitw/warroom/gateway/
└── controller/
    └── EpisodeControllerTest.java    # 🆕 contract test（happy + 404）

# Frontend
apps/warroom/src/
├── api/
│   └── episodes.ts                   # ✏ 確認 envelope mapper 對齊
├── viewmodels/
│   └── episode.ts                    # 既有 schema，read-only
└── pages/
    └── OverviewPage.tsx              # ✏ 移除 fixture fallback（若有）

# Tests
tests/
├── unit/
│   ├── ppo_training/
│   │   └── test_evaluate_trajectory_parquet.py   # 🆕
│   ├── scripts/
│   │   └── test_build_episode_artifact.py        # 🆕
│   └── inference_service/
│       └── test_episodes_store.py                # 🆕
├── integration/
│   └── inference_service/
│       └── test_episodes_endpoint.py             # 🆕（FastAPI TestClient）
└── contract/
    ├── inference_service/
    │   └── test_episodes_openapi.py              # 🆕（schema validation）
    └── episode_artifact/
        └── test_artifact_byte_identical.py       # 🆕（Principle I gate）

# Infra
infra/
├── Dockerfile.inference              # ✏ COPY episode_detail.json 進 image
└── docker-compose.gateway.yml        # 既有，無改動
```

**Structure Decision**: 沿用既有 monorepo 多 service 佈局；新增以 `scripts/build_episode_artifact.py` 為界，把 evaluator (`src/ppo_training/`) 與 inference service (`src/inference_service/`) 解耦。artefact 是兩者間唯一介面（檔案）。

## Phase 順序

### Phase 0：Research & Contract

對應 deliverable：`research.md`、`contracts/openapi-episodes.yaml`

決議項目：
1. **Trajectory persistence 格式**：parquet（zstd compressed）vs JSONL → 決議 parquet（schema 自描述、pandas 直讀、artefact builder side 開發成本最低）。同時保留 CSV legacy（向後相容 Colab）。
2. **Episode artefact 格式**：JSON vs MessagePack → 決議 JSON（人類可讀；< 10 MB 體積壓力小；對齊前端 zod schema）。`json.dumps(sort_keys=True, separators=(",", ":"))` 保證 byte-identical。
3. **EpisodeStore 載入策略**：lazy vs eager → eager（FR-012；fail fast）。lifespan startup 做一次：read JSON → validate against pydantic model → 存到 `app.state.episode_store`。
4. **OpenAPI 路徑**：對齊既有 envelope 風格（`{ items, meta }` for list；`{ data, meta }` for detail）。

### Phase 1：Evaluator trajectory.parquet 擴充

對應 deliverable：`src/ppo_training/evaluate.py` 變更 + 對應 unit test

工作項：
1. evaluator main loop 取 reward 四元（既有 `info["reward_components"]` 已含 `log_return`、`drawdown_penalty`、`cost_penalty`、`total_reward`；對齊 viewmodels/reward.ts naming）。
2. evaluator 取 action 四元：透過 `model.policy` 拿 raw / normalized 已有；新增 `log_prob` / `entropy`（PPO `policy.evaluate_actions(obs_tensor, action_tensor)` 回傳）。
3. evaluator 取 SMC signals 五元：`info["smc_signals"]`（環境已暴露；若沒有則 fallback 計算 — 確認後）。
4. 新 `--save-trajectory` 同時寫 `.parquet`（主檔）與 `.csv`（legacy）。
5. 寫 unit test：跑迷你 episode → 驗證 parquet schema、reward invariant、向後相容 CSV 仍可讀。

### Phase 2：Episode artefact builder

對應 deliverable：`scripts/build_episode_artifact.py` + 對應 unit test + byte-identical contract test

工作項：
1. 讀 trajectory.parquet + eval_summary.json + 6 個 OHLC parquet。
2. 對 6 檔資產各跑一次 `smc_features.batch.batch_compute_events`，產 SMCOverlay。
3. 組裝 `EpisodeDetailDto` JSON：summary（KPI）+ trajectoryInline（含 reward + action + smc per frame、ohlcvByAsset per frame）+ rewardBreakdown（byStep + cumulative）+ smcOverlayByAsset。
4. 序列化：`json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`。
5. 寫到 `runs/<run_id>/eval_oos/episode_detail.json`，同時複製到 `infra/inference/artefact/episode_detail.json`（Dockerfile build context）。
6. 計算並印出 sha256，作為 reproducibility 基線。
7. byte-identical contract test：跑兩次 builder，比對 sha256 == 才算 PASS。

### Phase 3：005 Inference Service endpoints

對應 deliverable：`src/inference_service/episodes.py` + `app.py` 路由 + integration test

工作項：
1. 新 `episodes.py`：`EpisodeStore` 類別，`load_from_path(path)` → 解析 JSON → 驗證 pydantic model → 提供 `list_summaries()` 與 `get_detail(id)`。
2. `app.py` lifespan：在現有 startup hook 之前/之後 load EpisodeStore；artefact 缺檔 → 拋例外 → uvicorn fail fast。
3. 兩個 endpoint：
   - `GET /api/v1/episodes` → 回 `{ items: [EpisodeSummaryDto], meta: {} }`
   - `GET /api/v1/episodes/{episode_id}` → 回 `{ data: EpisodeDetailDto, meta: {} }`；找不到回 404 + ApiErrorDto
4. integration test：FastAPI TestClient + 真實 artefact fixture，驗證 happy + 404。
5. contract test：openapi-episodes.yaml schema validation（`openapi-spec-validator` + `jsonschema`）。

### Phase 4：006 Spring Gateway proxy

對應 deliverable：`EpisodeController.java` + `EpisodeClient.java` + DTO + contract test

工作項：
1. `EpisodeClient`：WebClient bean 對 005 base url（既有 `inference-service:8000`）發 GET；timeout 5s。
2. `EpisodeController`：兩個 endpoint，純代理；錯誤碼透傳（404 → 404、其他 → 502）。
3. DTO：用 Java 25 record；`EpisodeDetailDto` 巢狀（trajectory frames、reward、smc）。
4. OpenAPI 對齊：在 gateway 既有 OpenAPI（若無則新增 `services/gateway/openapi.yaml`）加兩個 path。
5. WireMock 契約測試：mock 005 → 用 `WebTestClient` 打 gateway → 驗證 happy + 404 + 502 propagation。

### Phase 5：前端 envelope mapper + Overview wiring

對應 deliverable：`apps/warroom/src/api/episodes.ts` 確認 + Overview fixture fallback 移除 + vitest

工作項：
1. 確認 `toEpisodeSummary` / `toEpisodeDetail` 對齊 005 → gateway → 前端的 envelope 結構。
2. 移除 `OverviewPage.tsx` 中的 mock fixture fallback（如有）；改成 useQuery 回傳 error → 顯示明確錯誤狀態（FR-020）。
3. vitest：mapper unit test（缺欄位 → throw schema-violation；完整 payload → mapped viewmodel）。

### Phase 6：Image build + e2e smoke

對應 deliverable：`infra/Dockerfile.inference` 變更 + `quickstart.md` e2e 驗證

工作項：
1. `Dockerfile.inference`：`COPY infra/inference/artefact/episode_detail.json /app/episode_detail.json`；env `EPISODE_ARTEFACT_PATH=/app/episode_detail.json`。
2. `docker-compose.gateway.yml`：service env `EPISODE_ARTEFACT_PATH` 注入。
3. quickstart.md e2e：evaluator → builder → docker compose up → curl gateway → 開瀏覽器確認 Overview 頁有真實數據。

### Phase 7：測試 / lint / coverage

對應 deliverable：CI 全綠

工作項：
1. ruff + mypy clean。
2. pytest 三 marker（unit / integration / contract）全綠。
3. coverage：新增程式碼 ≥ 80%。
4. Java：`./mvnw test` 全綠。
5. frontend：`pnpm test` 全綠。

## 風險識別

| # | 風險 | 緩解 |
|---|---|---|
| R1 | **Parquet byte-identical 失敗**（pandas/pyarrow 寫 parquet 時 metadata 含 timestamp） | artefact 不直接 hash parquet；只 hash 最終 JSON。parquet 為中間產物。 |
| R2 | **JSON 序列化非確定性**（dict 順序、float repr） | 強制 `sort_keys=True`；float 統一用 `round(x, 12)` 後序列化；`allow_nan=False` 拒絕 NaN（NaN 序列化非標準）。 |
| R3 | **action.log_prob / entropy 取不到** | sb3 PPO `policy.evaluate_actions(obs_tensor, action_tensor)` 提供；若 wrapper 干擾，fallback 至 `policy.get_distribution(obs).log_prob(action)`。Phase 1 spike 確認。 |
| R4 | **SMC signals 五元在 env info 缺欄位** | 005 的 PortfolioEnv 既有暴露；若不全則由 artefact builder 用 008 SMC engine 補算（per-frame 取最近 swing 距離）。 |
| R5 | **Image 體積暴增**（artefact 5 MB × 6 OHLC parquet 重複塞） | OHLC 不打進 image，仍由 005 image 內 `data/raw` 提供（既有）；只塞 episode_detail.json。 |
| R6 | **frontend zod schema 不容忍未來 schema 漂移** | mapper 用 strict mode（zod `.strict()`）；任何未知欄位 → throw；API 契約只能 additive（破壞性變更走新 v2 endpoint）。 |
| R7 | **gateway 對 005 timeout** | WebClient timeout = 5s（detail 雖大但本地網路 + in-memory dict 序列化遠 < 1s）；timeout → 504 而非 hang。 |
| R8 | **artefact 路徑硬編碼造成測試難 mock** | `EPISODE_ARTEFACT_PATH` env 注入；test 給臨時 fixture 檔案。 |

## 不在範圍

- 重訓 PPO（屬 003-ppo-training-env）
- 修改 reward function / observation shape（屬 003 / 008）
- Episode CRUD（POST/PUT/DELETE）— 違反 spec out-of-scope
- 多 episode 並存 / 歷史 run 查詢
- training-loop dump（評估外的 episode 產生路徑）
- Overview UI 重畫（FR-020 只要求 schema 對齊、移除 fixture fallback）
- 多 policy 切換（屬 005 multi-policy reload，被 005 spec 標 SUPERSEDED）
- Kafka / Prometheus / TLS / JWT

## Complexity Tracking

> 無 violation；本區塊留空。
