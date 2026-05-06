# Implementation Plan: 推理服務（Inference Service）— C-lite 版

**Branch**: `005-inference-service` | **Date**: 2026-05-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-inference-service/spec.md`（2026-05-06 重寫）

## Summary

把 `src/ppo_training/predict.py` 包裝成 FastAPI 微服務（單一 ASGI process），同 process 內掛 APScheduler 每日 ET 16:30 自動觸發、HTTP `POST /infer/run` 接受 on-demand 重跑、`GET /infer/latest` 從 Redis 讀最新 cache、`GET /healthz` 給部署平台用。每次推理完成 publish 到 Redis pub/sub channel `predictions:latest` + 寫入 Redis key（TTL 7 天）。policy.zip + data/raw 在 Docker image build 時打包（無動態 reload），本機跑 docker-compose（python-infer + redis），後續上 Zeabur（managed Redis）。

技術核心：(a) **共用 inference handler** — scheduled / manual 兩條入口透過 asyncio.Lock 串行化，呼叫同一個 `run_inference()` async 函式（保證 FR-003 互斥 + SC-007 reproducibility）；(b) **prediction schema 對齊既有 `prediction_*.json`** — 透過共用 `PredictionPayload` Pydantic model 序列化，加 `triggered_by` + `inference_id` 欄位；(c) **Redis 解耦** — publish 失敗只 log，不影響 inference 結果寫入或回傳（FR-011）；(d) **DST 安全** — APScheduler 用 `pytz` ET timezone（不是 server local time）；(e) **container cold start ≤ 60s** — image build 時把 model + parquet 都 copy 進去（不掛 volume），避免冷啟動 download。

## Technical Context

**Language/Version**: Python 3.11+（與 003 / 004 / 008 對齊）
**Primary Dependencies**:
- `fastapi ~= 0.115`（ASGI app + 自動 OpenAPI）
- `uvicorn[standard] ~= 0.32`（ASGI server）
- `apscheduler ~= 3.10`（內建 cron + DST via pytz）
- `redis[hiredis] ~= 5.0`（async client，sync 版本同套件）
- `pydantic ~= 2.6`（與 002 / 003 對齊）
- `pytz ~= 2024.2`（ET timezone）
- 既有：`stable-baselines3 ~= 2.3`、`gymnasium`、`numpy`、`pyarrow`、`pandas`（從 003 / 004 import）

Dev: `pytest`, `pytest-asyncio`, `httpx`（async test client）, `fakeredis ~= 2.26`（unit test 用，避免起真 Redis），`testcontainers[redis] ~= 4.8`（integration test 用，真 Redis），`openapi-spec-validator`。

**Storage**: Stateless service。policy.zip + Parquet 由 image build 時 copy 進 `/app/runs/<run_id>/` + `/app/data/raw/`。執行階段唯一 stateful storage 是 Redis（外部、TTL 7 天、本機 sidecar / Zeabur managed）。

**Testing**: pytest + httpx async client + fakeredis（unit）+ testcontainers Redis（integration）。Coverage ≥ 85%（同 008 標準）。Contract test 比對 `predict.py` 產出 JSON schema 與 service `/infer/run` response 的 diff。

**Target Platform**: Linux x86_64 container（Python 3.11-slim base）。Phase 1 跑本機 Docker Desktop（macOS / Windows / WSL2 都可），Phase 2 跑 Zeabur（Linux container runtime）。

**Project Type**: web-service（HTTP microservice）

**Performance Goals**:
- `POST /infer/run` ≤ 90 秒（涵蓋 env warmup ~30s + step iteration ~5s + 緩衝）
- `GET /infer/latest` < 200 ms（cache 命中）/ < 50 ms（404）
- container cold start ≤ 60 秒（policy load + scheduler init，不含 first inference）
- scheduled trigger 誤差 ≤ 1 分鐘

**Constraints**:
- 部署不上 K8s — 不用 readiness/liveness probe 區分、不用 Prometheus pull、不用 ConfigMap
- 不用 Kafka — 用 Redis pub/sub（決策已鎖：見 memory `project_warroom_architecture_decisions.md`）
- 不做動態 policy reload — policy 換版要重 build image（容器化原則：image immutable）
- HTTP 不做 TLS（由 Zeabur ingress / 006 Spring Gateway 處理）
- 不做 auth（依賴 006 Gateway）
- 同時只允許一次 inference 跑（FR-003 mutex）

**Scale/Scope**:
- 一天 1~5 次 inference（1 scheduled + 偶爾 manual）
- 同時持有 1 個 default policy（~5 MB）
- 部署 1 個 replica（不做 horizontal scaling — 因 mutex + 業務量不需要）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

對齊 `.specify/memory/constitution.md` v1.1.0 五原則。三個 NON-NEGOTIABLE 原則展開為具體 gate items：

### Gate I — Reproducibility（NON-NEGOTIABLE）

- **G-I-1**: scheduled / manual 兩條觸發路徑 MUST 共用同一個 `run_inference()` 函式；該函式接受 `(triggered_by: str, inference_id: UUID)` 為唯一可變輸入，其餘（policy、data、env config、seed=42、`deterministic=True`）全部從啟動配置 inject、執行期不變動 → ✅ Plan 設計於 Phase 2 `handler.py`。
- **G-I-2**: prediction 結果包含可追溯欄位 `policy_path`, `data_root`, `as_of_date`, `n_warmup_steps`, `current_nav_at_as_of`, `inference_id`（schema 對齊 `predict.py` 產出 + 加 `inference_id` / `triggered_by`）→ ✅ FR-006 / FR-007 已要求。
- **G-I-3**: 同 policy.zip + 同 Parquet snapshot + `deterministic=True` 兩次跑出的 `target_weights` MUST byte-identical（容差 0.0）→ ✅ 對應 SC-007，Phase 7 contract test 自動驗證。
- **G-I-4**: container image 鎖定依賴版本 — `pyproject.toml` 加 `[inference]` optional group + 對應 `requirements-inference.txt` 由 `pip-compile` 產出，與 002 既有 `requirements-lock.txt` 同節奏 → ✅ Phase 1 task。

### Gate II — Explainability（弱適用）

- **G-II-1**: 本 service **不**新增 SMC 特徵（屬 008 範圍），但輸出之 `target_weights` MUST 來自合法 SMC observation 流（透過 `PortfolioEnv` import）。**不接受**「重寫一份簡化版 inference」走自己的 obs pipeline → ✅ Phase 2 `handler.py` 直接 reuse `predict.py` 的 env 構建邏輯，不 fork。

### Gate III — Risk-First Reward（NON-NEGOTIABLE）

- **G-III-1**: 本 service **不**改 reward function（屬 003 範圍）。任何 reward shaping / 後處理 MUST 拒絕 — service 只 forward policy.predict 結果 → ✅ Phase 2 `handler.py` 不引入 reward 計算。
- **G-III-2**: 輸出 `current_nav_at_as_of` 欄位（從 `PortfolioEnv.info["nav"]` 帶出）讓下游可追溯風險路徑 → ✅ FR-006 已要求。
- **G-III-3**: `target_weights` 一定通過 `PortfolioEnv` 的 `process_action` pipeline（NaN 檢查 / L1 normalize / position cap），與訓練時對齊 → ✅ Phase 2 `handler.py` 走 env.step 路徑、不直接調 model.predict 後就回傳。

### Gate IV — Service Decoupling

- **G-IV-1**: 本 service 對外只透過 HTTP（4 個 endpoint）+ Redis pub/sub。**禁止**直接讀寫 006 Spring Gateway 的 DB / 共享檔案系統 → ✅ FR-016 已排除。
- **G-IV-2**: 可在無 006 / 無 007 的環境下啟動並通過自身 contract test（fakeredis / testcontainers）→ ✅ Phase 7 task。
- **G-IV-3**: 憲法第 IV 條原文要求「Kafka 訊息」，但本 feature 採 Redis pub/sub（C-lite 路線決策）→ **Constitution Variance** 記錄於下方 Complexity Tracking。

### Gate V — Spec-First（NON-NEGOTIABLE）

- **G-V-1**: 本 plan 對應的 spec.md 已通過 review（2026-05-06 重寫版本）→ ✅。
- **G-V-2**: plan / tasks / implement 階段 **不得**新增 spec 未列的 endpoint（例如不可加 `/infer/history`、`/policies/list`）→ ✅ FR-016 已明確「不在範圍內」。
- **G-V-3**: 任何臨時加的 endpoint MUST 先回頭改 spec.md → /speckit.specify 重跑 → review → 才能寫 code → ✅ 流程約束。

### Constitution Variance — Kafka → Redis（Gate IV）

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution §IV 要求 Kafka，本 feature 用 Redis pub/sub 取代 | 本專案規模（一天 1~5 個 prediction event）+ 部署目標（docker-compose / Zeabur）+ 訂閱者數（1 個 Spring Gateway）完全不需要 Kafka 的持久化、partition、consumer group 機制；Kafka broker + ZooKeeper/KRaft 維運成本對單人研究專案過高 | Kafka 在本場景無功能優勢，只增加 deployment 複雜度與 Zeabur 不友善（要付 add-on）。決策已記錄於 memory `project_warroom_architecture_decisions.md`，並由 user（DaYi-TW）2026-05-06 明示確認 |

> 本變異 **不**觸發 constitution amendment（因為 §IV 屬於 NON-NEGOTIABLE 之外的原則），但 PR 描述需引用本 plan §Constitution Variance。

## Project Structure

### Documentation (this feature)

```text
specs/005-inference-service/
├── spec.md              # ✅ 2026-05-06 重寫
├── plan.md              # ⬅ 本檔（重寫中）
├── research.md          # Phase 0（將重寫）
├── data-model.md        # Phase 1（將重寫）
├── contracts/
│   ├── openapi.yaml     # Phase 1（將重寫，4 endpoints）
│   └── error-codes.md   # Phase 1（將重寫）
├── quickstart.md        # Phase 1（將重寫）
├── checklists/
│   └── requirements.md  # ✅ 2026-05-06 已對齊
└── tasks.md             # Phase 2 by /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── inference_service/                # NEW — 本 feature 全部新增於此
│   ├── __init__.py
│   ├── __main__.py                   # uvicorn entry: python -m inference_service
│   ├── config.py                     # ServiceConfig（從 env var 載入）
│   ├── handler.py                    # run_inference() 共用 handler — Phase 2 核心
│   ├── scheduler.py                  # APScheduler cron + DST + asyncio.Lock 註冊
│   ├── redis_io.py                   # async publisher + LatestCache 讀寫
│   ├── app.py                        # FastAPI app factory + 4 endpoints
│   └── schemas.py                    # PredictionPayload Pydantic model
├── ppo_training/                     # 既有 — 本 service import 不修改
│   ├── predict.py                    # 既有；inference_service.handler 會共用其建 env 邏輯
│   └── ...
├── portfolio_env/                    # 既有 — import 不修改
└── smc_features/                     # 既有 — import 不修改

tests/
├── contract/
│   └── inference_service/
│       ├── test_openapi_schema.py    # 驗證 openapi.yaml 符合 OpenAPI 3.1
│       └── test_prediction_schema_parity.py  # diff predict.py JSON vs service JSON
├── integration/
│   └── inference_service/
│       ├── test_inference_endpoint.py    # httpx + fakeredis
│       ├── test_redis_publish.py         # testcontainers redis
│       └── test_scheduler_dst.py         # APScheduler 行為（DST 邊界、mutex）
└── unit/
    └── inference_service/
        ├── test_handler_mutex.py
        ├── test_config.py
        └── test_schemas.py

infra/                                # NEW
├── Dockerfile.inference              # python-3.11-slim + policy + parquet
└── docker-compose.inference.yml      # python-infer + redis sidecar
```

**Structure Decision**: 採 single-project 結構（與 002 / 003 / 004 / 008 一致）。本 feature 全部代碼集中於 `src/inference_service/`，不切 mono-repo / sub-package。`infra/` 目錄為**本 feature 新建**，後續 006 Spring Gateway 也會放在 `infra/` 下（`Dockerfile.gateway`、`docker-compose.gateway.yml`）。

## Phase Plan

### Phase 1 — pyproject + skeleton（Setup）
- 在 `pyproject.toml` 新增 optional dependency group `[project.optional-dependencies] inference = [...]`
- 建立 `src/inference_service/` 全部 .py 檔骨架（空殼或最小 stub）
- 建立 `tests/{unit,integration,contract}/inference_service/` 目錄 + `conftest.py`
- 不寫真邏輯，只確保 `python -m inference_service --help` 不噴錯

### Phase 2 — config + handler core
- `config.py`：`ServiceConfig` Pydantic BaseSettings，從 env var 讀 `POLICY_PATH`、`DATA_ROOT`、`REDIS_URL`、`SCHEDULE_CRON`（預設 `30 16 * * MON-FRI` ET）、`INCLUDE_SMC`（預設 true）
- `schemas.py`：`PredictionPayload` Pydantic model，欄位 100% 對齊 `predict.py` 輸出 + 加 `triggered_by: Literal["scheduled","manual"]` + `inference_id: UUID`
- `handler.py`：核心 `run_inference(triggered_by: str) -> PredictionPayload`，內部：
  1. 用 `asyncio.Lock` 互斥
  2. 構建 PortfolioEnv（與 `predict.py` 同邏輯）
  3. 載入 PPO model 一次（process 啟動時，不每次重載）
  4. 跑完 episode 到資料尾、收 final action
  5. 序列化成 PredictionPayload
- **不**碰 FastAPI / Redis / scheduler — 純 logic

**單元測試**：mock policy + tiny dataset 驗證 (a) 兩次 call 結果 byte-identical、(b) lock 真互斥（同時 await 兩個會有 latency）

### Phase 3 — HTTP layer
- `app.py`：`create_app() -> FastAPI`
- 4 endpoints：
  - `POST /infer/run` → 呼叫 handler，回 PredictionPayload，`triggered_by="manual"`
  - `GET /infer/latest` → 從 redis_io 讀，404 if 空
  - `GET /healthz` → 200 + `{"status":"ok","uptime_seconds":int,"policy_loaded":bool}`
  - `GET /openapi.json` → FastAPI 自動產
- `__main__.py`：uvicorn boot

**整合測試**：httpx + fakeredis，驗證 4 endpoints 行為。

### Phase 4 — scheduler
- `scheduler.py`：APScheduler `AsyncIOScheduler` + `CronTrigger.from_crontab` + `pytz.timezone("America/New_York")`
- 觸發時呼叫 `handler.run_inference(triggered_by="scheduled")`，再呼叫 redis_io.publish
- 單次失敗 log + 不停 scheduler（FR-010）
- 與 FastAPI 同 event loop（lifespan startup/shutdown 註冊）

**整合測試**：mock APScheduler 把 trigger time 改成 1 秒後，驗證 (a) trigger fire、(b) failure 後下次仍 fire、(c) DST 切換日的 next_run_time 計算正確

### Phase 5 — Redis publisher + LatestCache
- `redis_io.py`：async redis client wrapper
  - `publish_prediction(payload)` → SET key `predictions:latest` (TTL 604800) + PUBLISH channel `predictions:latest`
  - `get_latest()` → GET key，None if 空 / expired
  - publish 失敗只 log（FR-011）
- handler 完成後在 app layer 串接（不在 handler 內，保持 handler 純粹）

**整合測試**：testcontainers redis，pub/sub round-trip 驗證

### Phase 6 — Dockerfile + docker-compose
- `infra/Dockerfile.inference`：
  - base `python:3.11-slim`
  - copy `pyproject.toml`, `src/`, `runs/<run_id>/final_policy.zip`, `data/raw/*.parquet`
  - install `pip install .[inference]`
  - `CMD ["python", "-m", "inference_service"]`
- `infra/docker-compose.inference.yml`：
  - `python-infer` service + `redis:7-alpine` sidecar
  - env var pass policy path + redis url
  - healthcheck on `/healthz`

**Smoke test**：`docker compose up` → curl `/healthz` 200 → curl `POST /infer/run` 90 秒內回 200

### Phase 7 — Tests + Polish
- Coverage ≥ 85%
- ruff + mypy 全綠
- README 加一段「How to run inference service locally」

## Risks

| 風險 | 影響 | 緩解 |
|------|------|------|
| **觸發互斥** scheduled / manual 同時跑會搶 env state | reproducibility 破功 | `asyncio.Lock` 包 handler；第二個 await 排隊；若不耐久候則回 503 + Retry-After |
| **DST 切換** APScheduler 用 server local time 會在 3/9 與 11/2 漏跑或重複跑 | SC-002 7 天無漏跑會掛 | 顯式用 `pytz.timezone("America/New_York")` 不用 `tzlocal`；integration test 模擬 DST 邊界 |
| **Redis 斷線** publish 失敗時整個 inference 算失敗 | 容錯破功 | redis_io.publish 包 try/except，失敗只 log + 結果仍寫 LatestCache（嘗試）+ 仍從 endpoint 回傳 caller |
| **prediction schema 漂移** service 序列化跟 `predict.py` 不一致 | 前端 parser 會壞 | Phase 7 contract test：跑一次 `predict.py` 產 ground truth JSON、跑一次 service `/infer/run`、對 diff（除了 `triggered_by` / `inference_id` 欄位外完全一致）|
| **container cold start** policy load + parquet load 超過 60s | Zeabur health probe 失敗 | image build 時 copy 進去（不 download）；policy lazy-load 改 eager（process 啟動時就載入完）；`/healthz` 在 policy 還沒載完時回 503 但 process 不掛 |
| **neutral trend 初始 BOS 邊界**（屬 008 既有風險） | 不影響本 feature | 008 已收 |
| **Spring Gateway 時序耦合** 006 還沒做就先跑本 service | 訂閱者為空 → 沒人收 publish | publish 不阻塞、cache 仍寫；006 上線後重連即可從 cache 拉到最新 |

## Out of Scope

- Spring Gateway integration（屬 006）
- 前端 LivePredictionCard / SSE 接線（屬 007 收尾）
- Kafka（明確排除）
- Prometheus metrics（不在 MVP；future）
- TLS termination（由 ingress / Zeabur 處理）
- JWT / auth（依賴 006）
- multi-policy 動態切換（policy 換版重 build image）
- episode replay endpoint（feature 005 舊版範圍，已移除）
- horizontal scaling / multi-replica（mutex 設計就是 single-instance）
- monitoring dashboard / alerting（future）
