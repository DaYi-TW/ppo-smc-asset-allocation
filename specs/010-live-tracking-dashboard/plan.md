# Implementation Plan: PPO Live Tracking Dashboard

**Branch**: `010-live-tracking-dashboard` | **Date**: 2026-05-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/010-live-tracking-dashboard/spec.md`

## Summary

把 007 戰情室 Overview 從「OOS 回測展示」轉為「每日真實 prediction tracking dashboard」當產品看待。新增一份 **mutable** artefact `runs/<policy_run_id>/live_tracking/live_tracking.json`（schema 重用 009 已定型的 `EpisodeDetail`），起始 frame 對應 2026-04-29（OOS 結束日 2026-04-28 後第一個 NYSE 交易日），起始 NAV 接續 1.7291986。提供 `scripts/run_daily_tracker.py` 跑 daily pipeline（fetch → inference → single-step env → append frame → 全段重算 SMC overlay → atomic write）。005 加 `POST /api/v1/episodes/live/refresh` 與 `GET /api/v1/episodes/live/status` 兩個 endpoint，並把既有 `GET /episodes` 與 `GET /episodes/{id}` 擴成 OOS + Live 雙來源。006 1:1 反向代理新增的兩個 endpoint。007 OverviewPage 預設改顯示 Live、加「手動更新到最新」按鈕、加「資料截至 N 天前」徽章、加失敗 toast。**禁止**重訓 PPO、改 reward、改 observation shape、改 SMC engine 內部、改 009 builder。

## Technical Context

**Language/Version**:
- Python 3.11（daily tracker pipeline + 005 endpoint 擴充；對齊既有 `pyproject.toml` 與 dev container）
- Java 25 LTS + Spring Boot 4.x（006 gateway proxy；對齊 constitution Technology Stack）
- TypeScript 5.x + React 18（007 OverviewPage；既有專案）

**Primary Dependencies**:
- Python：`pandas`、`numpy`、`pyarrow`（既有）；`stable-baselines3`（既有，policy load）；**新加** `pandas_market_calendars`（NYSE holiday 含半日市；標準業界用法、Python 3.11 wheel 無 native deps）；`structlog` 已在 005（observability）
- 005：`fastapi`、`pydantic v2`、`uvicorn`、`apscheduler`、`redis.asyncio`（皆既有）；新增 `asyncio.Lock` 控並發、`fastapi.BackgroundTasks` 跑 pipeline
- 006：`spring-boot-starter-webflux`（既有）；既有 `EpisodeClient` 擴充
- 007：`@tanstack/react-query`、`zod`（既有）；polling 用 react-query 既有 `refetchInterval`

**Storage**:
- Live artefact：**單一 mutable JSON 檔** `runs/<policy_run_id>/live_tracking/live_tracking.json`（與 OOS 同 schema、同序列化規則）
- Status 中繼資料：與 artefact 並列的 `live_tracking_status.json`（小 JSON：last_updated / last_frame_date / is_running / last_error）
- 寫入策略：`tmp + os.replace` atomic write，重用 `src/data_ingestion/atomic.py` 的 `staging_scope` + `atomic_publish` 模式
- **不**塞進 Docker image（與 OOS 不同）；走 host volume mount 進 005 container（compose `volumes:`）；Zeabur 階段切換到對應的 persistent volume，屬下個 feature
- 不引入資料庫（單檔 + status 檔已足夠；append-only 語意天然契合「整檔重寫」模式）

**Testing**:
- Python unit / integration / contract：pytest（marker：`-m unit|integration|contract`）；既有測試骨架
- pipeline test 用 `freezegun` mock today、用 in-memory stub OHLCV、用 sb3 policy fixture
- Java：JUnit 5 + Spring `WebTestClient` + WireMock（既有）
- Frontend：Vitest + Testing Library；polling test 用 `vi.useFakeTimers()`

**Target Platform**: Linux container（Docker compose 本地）；前端 evergreen browser
**Project Type**: 既有 monorepo 多 service 佈局
**Performance Goals**:
- pipeline 跑 1 天新資料 ≤ 60 秒（SC-006 上界）；跑 7 天新資料 ≤ 180 秒
- `GET /api/v1/episodes/live/status` 回應 ≤ 100 ms（純讀檔 + 計算 lag days）
- `POST /api/v1/episodes/live/refresh` 回應 ≤ 500 ms（202 Accepted；不等 pipeline）
- Overview 首屏 ≤ 5 秒（同 SC-006）

**Constraints**:
- artefact append-only：歷史 frame 一旦寫入不可被改寫（FR-003），但 SMC overlay / summary metrics 每次重算（FR-004 / FR-005）
- 並發保護：asyncio.Lock 確保 single-flight；第二個 refresh 立即 409（FR-006）
- 失敗回滾：原子寫入確保失敗時 artefact 維持上次成功狀態（FR-009）
- 起始錨點：2026-04-29（OOS 結束 +1 NYSE trading day）；起始 NAV 1.7291986（OOS 終值）；硬編於 config，不允許隨意調整（避免破壞學術 baseline 銜接）
- **不**改 reward function（Principle III, NON-NEGOTIABLE）：pipeline 必須 import 既有 `portfolio_env.env.PortfolioEnv` 的同一個 reward 計算路徑
- **不**改 observation shape / env step 邏輯（Principle V）

**Scale/Scope**:
- 單一 active policy；單一 live artefact；< 100 frames/year（每年 ~252 個交易日，但本 feature 預期最多累積數月）
- 估計 LOC 變更：daily tracker pipeline +400、005 endpoint +200、status state machine +150、006 controller +120、frontend hook + Overview wiring +250

## Constitution Check

> 對齊 `.specify/memory/constitution.md` v1.1.0（2026-04-29 ratified）。三 NON-NEGOTIABLE 原則必須通過 gate；其餘原則記錄合規狀態。

| # | 原則 | 狀態 | 說明 |
|---|---|---|---|
| **I** | **Reproducibility（NON-NEGOTIABLE）** | ✅ PASS（with explicit scoping）| 本 feature 引入 mutable artefact `live_tracking.json`，每次 refresh 必然改變內容（新增 frame + 全段重算 overlay/summary），**明確不**要求 byte-identical sha256。但 spec FR-014 / SC-008 強制 OOS episode_detail.json 維持 byte-identical 作為學術 baseline。**Gate item**：(a) 寫一條 contract test 連續 5 次讀 OOS episode detail → sha256 必須相同（已存在於 009 contract test，本 feature 不破壞）；(b) live tracking 不寫該 test，而是寫「append-only 不改寫歷史 frame」test（FR-003）：mock 某日 inference 後比對 N-1 frame 與前次完全一致；(c) pipeline 內所有計算（reward、SMC、env step）seed-fixed（沿用既有 PPO env 的 seed=42）。Range 區隔以 `tests/contract/episode_artifact/test_oos_immutable_hash.py` 與 `tests/contract/live_tracking/test_append_only.py` 分檔表達。 |
| **II** | Explainability | ✅ PASS | (a) Live artefact 沿用 OOS 同 schema：reward 三元拆解、SMC overlay 結構化、ohlcvByAsset per frame 全部出現，前端 Overview 對 Live / OOS 渲染路徑一致。(b) SMC overlay 重算用 008 `batch_compute_events`，與 OOS 完全相同規則，不漂移。(c) 每日 frame 的 action raw / normalized / log_prob / entropy 四元保留，可逐日復盤模型決策。 |
| **III** | **Risk-First Reward（NON-NEGOTIABLE）** | ✅ PASS | (a) 本 feature **禁止**修改 reward function。pipeline 透過 `from portfolio_env.env import PortfolioEnv` import 既有 env 並 `env.step()`，由 env 內部 reward function 計算每日 frame 的 returnComponent / drawdownPenalty / costPenalty / total。(b) **Gate item**：寫一條 unit test，mock 一個固定 action，比對 pipeline 跑出來的 reward 三元與「直接呼叫 PortfolioEnv 跑同 step」結果完全相同（assertEqual + 1e-9 容差）；任何複製或近似 reward 計算的 PR MUST 被該 test 擋下。(c) reward components schema 沿用 009 的 `RewardComponents` pydantic 型別（強制三項都出現，無 single scalar 簡化）。 |
| **IV** | Service Decoupling | ✅ PASS | (a) 005 ↔ 006 ↔ 007 仍走 HTTP/REST。(b) Live artefact 是 005 容器內的 mutable file，**不**做為跨 service 共享 volume；006 / 007 透過 005 endpoint 取得內容，不直接讀檔。(c) daily tracker pipeline 跑在 005 process 內（FastAPI BackgroundTasks），不引入額外 service / 額外 process / Kafka topic。(d) 每個 service 仍可在隔離容器啟動測試（005 用 fake artefact dir、006 用 WireMock stub 005、007 用 vitest fixture）。 |
| **V** | **Spec-First（NON-NEGOTIABLE）** | ✅ PASS | (a) `specs/010-live-tracking-dashboard/spec.md` 已通過 quality checklist 16/16。(b) 兩個新 endpoint 完全由 FR-015 / FR-016 定義；契約檔 `contracts/openapi-live-tracking.yaml` 為 implementation 唯一依據。(c) **Gate item**：refresh endpoint 回 202 + `estimated_duration_seconds`（FR-016 強制）；status endpoint 欄位嚴格 = `last_updated / last_frame_date / data_lag_days / is_running / last_error`（FR-015 列舉）。任何「實作時臨時加欄位 / 加 endpoint」MUST 先回 spec 補 FR；本 feature 禁止 PUT/DELETE、禁止暴露 pipeline 內部步驟、禁止暴露 mutex 狀態以外的 metadata。 |

**Gate verdict**: ✅ All NON-NEGOTIABLE 通過；無 violation；`Complexity Tracking` 留空。

## Project Structure

### Documentation (this feature)

```text
specs/010-live-tracking-dashboard/
├── plan.md                          # 本檔案
├── research.md                       # Phase 0：原子寫入 / NYSE 交易日曆 / single-step env 推進 / SMC 重算成本
├── data-model.md                     # Phase 1：5 個 entity（LiveArtefact / Status / Pipeline / Trigger / ListItem）
├── contracts/
│   └── openapi-live-tracking.yaml    # /live/refresh + /live/status OpenAPI 3.1
├── quickstart.md                     # Phase 1：本機 e2e（compose up → curl refresh → 驗 frames 補齊 → 開 Overview）
├── checklists/
│   └── requirements.md               # specify 階段已完成（16/16 ✓）
└── tasks.md                          # /speckit.tasks 產出
```

### Source Code (repository root)

```text
# Python AI 引擎（共用）
src/
├── live_tracking/                    # 🆕 套件根
│   ├── __init__.py                   # 🆕
│   ├── pipeline.py                   # 🆕 DailyTrackerPipeline 主體（fetch→infer→step→append→overlay→write）
│   ├── store.py                      # 🆕 LiveTrackingStore（read/append/atomic write）
│   ├── status.py                     # 🆕 LiveTrackingStatus state machine（檔案持久化、recovery）
│   ├── calendar.py                   # 🆕 wrap pandas_market_calendars，純函數 missing_trading_days(start, end)
│   └── inference.py                  # 🆕 single-step PPO inference helper（無 episode loop，只一步）
├── inference_service/
│   ├── app.py                        # ✏ 加 lifespan hook 初始化 LiveTrackingStore + Status；加 2 個新 route
│   ├── live_endpoints.py             # 🆕 POST /live/refresh + GET /live/status handlers + asyncio.Lock
│   ├── episodes.py                   # ✏ 改成支援 OOS + Live 雙來源（既有 EpisodeStore 重構為 multi-source）
│   ├── episode_schemas.py            # ✏ 加 LiveTrackingStatusDto + RefreshAcceptedDto
│   └── config.py                     # ✏ 加 LIVE_ARTEFACT_DIR / LIVE_START_DATE / LIVE_INITIAL_NAV env
└── ppo_training/                     # ❌ 不動（reward / env / observation / trainer）
└── smc_features/                     # ❌ 不動（008 SMC engine）

scripts/
└── run_daily_tracker.py              # 🆕 CLI wrapper：python -m live_tracking.pipeline --once（manual / smoke 用）

# Java Gateway
services/gateway/src/main/java/com/dayitw/warroom/gateway/
├── controller/
│   └── EpisodeController.java        # ✏ 加 GET /api/v1/episodes/live/status + POST /live/refresh proxy
├── dto/
│   ├── LiveTrackingStatusDto.java    # 🆕
│   └── RefreshAcceptedDto.java       # 🆕
└── service/
    └── EpisodeClient.java            # ✏ 加 fetchLiveStatus() + triggerLiveRefresh()

services/gateway/src/test/java/com/dayitw/warroom/gateway/
└── controller/
    └── EpisodeControllerLiveTest.java # 🆕 contract test（happy + 409 + 502 propagation）

# Frontend
apps/warroom/src/
├── api/
│   ├── episodes.ts                   # ✏ 加 fetchLiveStatus() + triggerRefresh()
│   └── envelopes.ts                  # ✏ 加 toLiveTrackingStatus mapper
├── hooks/
│   └── useLiveRefresh.ts             # 🆕 react-query mutation + status polling 組合
├── components/
│   └── overview/
│       ├── LiveRefreshButton.tsx     # 🆕 「手動更新到最新」+ disabled state + spinner
│       └── DataLagBadge.tsx          # 🆕 「資料截至 N 天前」徽章
└── pages/
    └── OverviewPage.tsx              # ✏ 預設 episode = live；加 header 控件；加失敗 toast

# Tests
tests/
├── unit/
│   ├── live_tracking/
│   │   ├── test_calendar.py          # 🆕 NYSE missing days 邏輯
│   │   ├── test_status.py            # 🆕 state machine + 持久化 + recovery
│   │   ├── test_store.py             # 🆕 atomic write / append-only / load
│   │   ├── test_pipeline.py          # 🆕 主邏輯：fetch+infer+step+append+overlay+write
│   │   └── test_inference.py         # 🆕 single-step inference helper
│   └── inference_service/
│       └── test_live_endpoints.py    # 🆕 handler 邏輯（mock store + status）
├── integration/
│   └── inference_service/
│       └── test_live_refresh_flow.py # 🆕 FastAPI TestClient e2e（mock 資料源 + 真 pipeline）
└── contract/
    ├── inference_service/
    │   └── test_live_openapi.py      # 🆕 schema validation
    ├── episode_artifact/
    │   └── test_oos_immutable_hash.py    # 🆕（Principle I gate for OOS）
    └── live_tracking/
        ├── test_append_only.py            # 🆕（Principle I gate for Live：歷史 frame 不被改寫）
        └── test_reward_parity.py          # 🆕（Principle III gate：pipeline reward == env step reward）

# Infra
infra/
├── docker-compose.gateway.yml         # ✏ 005 service 加 volume mount: ./runs:/app/runs
├── docker-compose.inference.yml       # ✏ 同上
└── Dockerfile.inference               # ❌ 不動（live artefact 不打進 image）
```

**Structure Decision**: 沿用既有 monorepo。新增 `src/live_tracking/` 套件作為 daily pipeline 的純 Python 邏輯邊界（不依賴 FastAPI；可獨立用 `python -m live_tracking.pipeline` 跑）。005 inference service 只擴 endpoint 與 lifespan，不把 pipeline 邏輯嵌進 web layer，保持 testability。

## Phase 順序

### Phase 0：Research

對應 deliverable：`research.md`

決議項目：
1. **Atomic write 跨平台一致性**：`os.replace` on Windows 是否原子 → 重用既有 `src/data_ingestion/atomic.py` `staging_scope` 模式（已驗證 Windows 友善訊息）。寫 `live_tracking.json.tmp` → fsync → `os.replace()` → fsync 父目錄。decision recorded in research.md。
2. **NYSE 交易日曆來源**：`pandas_market_calendars` vs 自建 holiday 表 → 決議 `pandas_market_calendars`（業界標準、含半日市、Python 3.11 wheel）。calendar.py 只暴露 `missing_trading_days(last_frame_date, today)` 純函數。
3. **Single-step env 推進策略**：直接呼叫 `PortfolioEnv.step(action)` vs 自寫 NAV 推進 → 決議呼叫 env（Principle III gate item：reward 必須由同一函數計算）。env 重新 reset 到 `initial_nav=last_frame.nav` 的位置，feed 最新 obs，執行一步。
4. **SMC overlay 全段重算成本**：每次 refresh 對 N + 已有 frames 跑 6 個 asset 的 `batch_compute_events` → 估算 ≤ 2 秒（已驗證 329 frames × 6 assets 在 008 engine 下 < 1 秒；append 後規模 < 400 frames）。recorded as performance budget。
5. **Live id 命名**：`<policy_run_id>_live`（例如 `20260506_004455_659b8eb_seed42_live`），與 OOS id 不同（後者無 `_live` 後綴）。EpisodeList 排序：OOS 在前（穩定性錨點）、Live 在後。
6. **Status 持久化策略**：與 artefact 同目錄 `live_tracking_status.json`（小 JSON）；啟動時讀檔；若 `is_running == True` 但 process 重啟（孤兒 lock）→ 啟動時 reset 為 False + 清理 .tmp 殘留檔。
7. **Pipeline 中途失敗錯誤分類**：(a) 資料源失敗（fetch yfinance / parquet 缺資產欄位）；(b) inference 失敗（policy load fail / env step exception）；(c) 寫檔失敗（disk full / permission）。三類都走同一 rollback path（不寫入既有 artefact）+ 在 status.last_error 標記原因。
8. **OOS + Live 雙來源 EpisodeStore 重構**：既有 009 `EpisodeStore` 是 single-episode；本 feature 重構為 `MultiSourceEpisodeStore`，內含一個 `OOSEpisodeStore`（既有邏輯）+ 一個 `LiveTrackingStore`（新）；list 回 1 ~ 2 筆（依 Live 是否已建立）。

### Phase 1：Setup（calendar、status state machine、store skeleton）

對應 deliverable：`src/live_tracking/calendar.py`、`status.py`、`store.py` 骨架 + 對應 unit test（紅）

工作項：
1. 新 `src/live_tracking/__init__.py` 套件入口。
2. `calendar.py`：`missing_trading_days(last_frame_date: date, today: date) -> list[date]` 純函數；採 `pandas_market_calendars.get_calendar("NYSE")`。
3. `status.py`：`LiveTrackingStatus` dataclass + `load(path) / write(path)`；`mark_running()` / `mark_succeeded(last_frame_date)` / `mark_failed(error_msg)`；recovery 邏輯：load 時若 `is_running=True` 且 PID 不存在或啟動時間早於本 process → reset。
4. `store.py`：`LiveTrackingStore`，`load(path) -> EpisodeDetailEnvelope | None`（檔案不存在回 None；存在則 strict-validate）、`atomic_write(envelope, path)`（重用 atomic.py）；read 路徑提供 `frames(): list[Frame]` 與 `last_frame_date(): date | None`。
5. 寫 unit test（紅）：calendar 跨假日、status state transitions、store atomic write & rollback。

### Phase 2：Daily pipeline core

對應 deliverable：`src/live_tracking/pipeline.py` + `inference.py` + `scripts/run_daily_tracker.py` + 對應 unit + integration test

工作項：
1. `inference.py`：`single_step_inference(policy, obs) -> ActionResult`；包 sb3 `policy.predict` + `policy.evaluate_actions` 取 log_prob/entropy。
2. `pipeline.py`：`DailyTrackerPipeline.run_once(today: date) -> PipelineResult`：
   - 讀 status；若 `is_running` → raise RefreshInProgressError
   - 標記 status `is_running=True`、寫檔
   - load store（不存在 → 用 OOS 終值 1.7291986 + 起始日 2026-04-29 初始化空 envelope）
   - calendar 算 missing days
   - 若無缺漏日 → 標記 status `succeeded`、return `result(no_op=True)`
   - 對每個 missing day 跑：fetch OHLCV → reset env to last_frame → step → produce frame
   - 把所有新 frames append 到 envelope
   - 對整段 trajectory 跑 6-asset `batch_compute_events`，覆蓋 smcOverlayByAsset
   - 重算 summary metrics（finalNav / cumReturn / maxDrawdown / sharpe / sortino）
   - atomic write artefact + status `succeeded`
   - 任何例外 → status.last_error + raise；store atomic write 保證 artefact 維持上次成功狀態
3. `scripts/run_daily_tracker.py`：CLI wrapper（manual smoke 用），呼叫 `DailyTrackerPipeline.run_once(date.today())`。
4. 寫 unit test（紅）：no-op case、多日補齊、reward parity、append-only、整體失敗回滾。
5. 寫 integration test：mock yfinance + 真 pipeline + 真 store + 真 env → 驗證 artefact 內容。

### Phase 3：005 endpoints + lifespan + asyncio.Lock

對應 deliverable：`src/inference_service/live_endpoints.py` + `app.py` lifespan 變更 + endpoint contract test

工作項：
1. `episodes.py` 重構：`MultiSourceEpisodeStore`，內含 `oos: EpisodeStore | None`（既有）+ `live: LiveTrackingStore | None`；`list_envelope()` 合併兩來源；`get_envelope(id)` dispatch by id suffix。
2. `live_endpoints.py`：
   - `POST /api/v1/episodes/live/refresh`：取 module-level `asyncio.Lock`；若 locked → 409 + `RefreshInProgressDto`；否則 schedule `BackgroundTasks` 跑 pipeline，立即回 202 + `RefreshAcceptedDto{ accepted_at, estimated_duration_seconds }`。
   - `GET /api/v1/episodes/live/status`：讀 status state machine + 計算 `data_lag_days = (today - last_frame_date).days` → 回 `LiveTrackingStatusDto`。
3. `app.py` lifespan：startup 時初始化 `MultiSourceEpisodeStore` + `LiveTrackingStatus`；status recovery（清理孤兒 is_running + .tmp）；register `live_router`。
4. `episode_schemas.py` 加 `LiveTrackingStatusDto` + `RefreshAcceptedDto` + `RefreshInProgressDto`，pydantic v2 with `extra='forbid'`。
5. `config.py` 加 env：`LIVE_ARTEFACT_DIR`（default `/app/runs/<run_id>/live_tracking`）、`LIVE_START_DATE`（default 2026-04-29）、`LIVE_INITIAL_NAV`（default 1.7291986）。
6. 寫 contract test：openapi-live-tracking.yaml schema 驗證、refresh 409 happy path、status 欄位 strict（多/少欄位都 fail）。

### Phase 4：006 Spring Gateway proxy

對應 deliverable：`EpisodeController` 擴充 + `EpisodeClient` 擴充 + Java DTO + WireMock contract test

工作項：
1. `EpisodeClient`：加 `fetchLiveStatus()` + `triggerLiveRefresh()` 方法；timeout 5s；錯誤映射到 `InferenceServiceException` / `InferenceTimeoutException` / `InferenceBusyException`（既有）。
2. `EpisodeController`：加 `GET /api/v1/episodes/live/status` + `POST /api/v1/episodes/live/refresh` 純代理；錯誤碼透傳：404 → 404、409 → 409、其他 → 502。
3. Java DTO：`LiveTrackingStatusDto`（record）+ `RefreshAcceptedDto`（record）+ `RefreshInProgressDto`（record）。
4. OpenAPI 對齊：`services/gateway/openapi.yaml` 加兩個 path（與 005 contracts/openapi-live-tracking.yaml 一致）。
5. WireMock 契約測試：mock 005 → 用 `WebTestClient` 打 gateway → 驗 happy + 409 + 502 propagation + lifespan ready < 60 秒（SC 沿用 006 既有）。

### Phase 5：前端 Overview wiring + polling hook + 失敗 toast

對應 deliverable：`useLiveRefresh.ts` hook + `LiveRefreshButton` + `DataLagBadge` + `OverviewPage` 改寫 + vitest

工作項：
1. `api/episodes.ts`：加 `fetchLiveStatus()`（GET）+ `triggerRefresh()`（POST → return 202 envelope）。
2. `api/envelopes.ts`：加 `toLiveTrackingStatus(dto) → ViewModel`（zod strict validation）。
3. `hooks/useLiveRefresh.ts`：react-query `useMutation` for trigger + `useQuery` with `refetchInterval` for status polling（pipeline 跑時每 3s 一次，閒時 60s 一次）；mutation success → invalidate episode detail query。
4. `components/overview/LiveRefreshButton.tsx`：點擊呼叫 mutation；disabled when `is_running=true`；spinner state；失敗 toast（FR-025）。
5. `components/overview/DataLagBadge.tsx`：基於 `status.data_lag_days` 顯示文字（0 → 「最新」；1 → 「1 天前」；N → 「N 天前」）。
6. `pages/OverviewPage.tsx`：default episode 改用 live id（or fallback to 「Live tracking 尚未啟動」引導）；header 加上述兩個元件。
7. vitest：mapper test、hook integration test（fake timers）、Button disabled state test。

### Phase 6：Infra 變更 + e2e smoke

對應 deliverable：`docker-compose.gateway.yml` / `docker-compose.inference.yml` 加 volume + `quickstart.md` e2e

工作項：
1. `docker-compose.inference.yml`：005 service 加 `volumes: ["./runs:/app/runs"]`；env 加 `LIVE_ARTEFACT_DIR=/app/runs/${POLICY_RUN_ID}/live_tracking`。
2. `docker-compose.gateway.yml`：同上。
3. quickstart.md e2e：
   - `docker compose -f infra/docker-compose.gateway.yml up --build -d`
   - `curl POST /live/refresh` → 202
   - polling `GET /live/status` 直到 `is_running=false`
   - `curl GET /episodes` 應回 2 筆（OOS + Live）
   - `curl GET /episodes/<live_id>` 應回 trajectoryInline ≥ 1 frame
   - 開瀏覽器 http://localhost:5173 → Overview 預設顯示 Live、徽章顯示「最新」
   - 模擬「資料 N 天前」：手動把 status.last_frame_date 改成 N 天前 → 重整 → 徽章顯示「N 天前」

### Phase 7：測試 / lint / coverage / Constitution gate 驗收

對應 deliverable：CI 全綠 + Constitution gate test 全綠

工作項：
1. ruff + mypy clean。
2. pytest 三 marker 全綠（unit / integration / contract）。
3. coverage：新增程式碼 ≥ 80%。
4. Java：`./mvnw test` 全綠。
5. Frontend：`pnpm test` 全綠。
6. **Constitution gate 專屬測試**：
   - `tests/contract/episode_artifact/test_oos_immutable_hash.py`：連 5 次讀 OOS detail → sha256 相同。
   - `tests/contract/live_tracking/test_append_only.py`：mock 兩次 refresh → 第一次的 N frames 在第二次後仍存在且內容相同（只新增不改寫）。
   - `tests/contract/live_tracking/test_reward_parity.py`：固定 action + obs，pipeline 跑出的 reward 三元 == 直接呼叫 PortfolioEnv.step 的 reward 三元（1e-9 容差）。
   - 驗 Spec FR-001 ~ FR-027 各對應至少一個 test。

## 風險識別

| # | 風險 | 緩解 |
|---|---|---|
| R1 | **原子寫入跨平台**（os.replace on Windows 對 antivirus 持有檔案會失敗） | 重用 `src/data_ingestion/atomic.py` `staging_scope`（已含 Windows-friendly 訊息）；在啟動時清理孤兒 `.staging-*` 與 `.tmp` 殘留。 |
| R2 | **NYSE 半日市 / 假期清單漂移** | 用 `pandas_market_calendars` 而非自建表；calendar.py 純函數可單測；定期升級 wheel 版本對齊監管。 |
| R3 | **single-step env 推進偏離 OOS 評估邏輯** | pipeline 必須呼叫同一個 `PortfolioEnv` instance，禁止複製 reward / NAV 推進；reward parity contract test（Principle III gate）擋下任何近似實作。 |
| R4 | **SMC overlay 全段重算成本暴增**（trajectory 累積到 1000 frames） | 估算 6 assets × 1000 frames 在 008 engine ≤ 5 秒；MVP 預期 frames < 400；若實際成本超標屬未來 feature（incremental overlay 重算），不在本 feature 範疇。 |
| R5 | **asyncio.Lock 不跨 process 持久** | status 檔案 `is_running` 為唯一持久 mutex；process restart 時的 lifespan recovery 強制 reset；雙保險：lock 用於 in-process 並發拒絕（快速 409），status.is_running 用於跨 restart consistency。 |
| R6 | **Live id 與 OOS id 衝突** | 命名規則 `<policy_run_id>_live` 寫死於 config + `episode_schemas.py` 校驗；EpisodeList 排序固定 OOS first。 |
| R7 | **失敗回滾不完整**（pipeline 寫到一半 process kill） | 寫入永遠走 `tmp + os.replace`，artefact 任一時刻只可能是「上次成功版」或「新成功版」；lifespan recovery 清理 `.tmp` 殘留。 |
| R8 | **資料源 yfinance / parquet 不穩定**（網路 / api 限流） | pipeline 失敗時 status.last_error 標記具體錯誤分類（DATA_FETCH / INFERENCE / WRITE）；前端 toast 顯示分類訊息，不吞錯。 |
| R9 | **policy.zip 載入策略**（pipeline 與既有 inference handler 共用？） | 重用 005 既有 lifespan-loaded policy（`app.state.policy`）；pipeline 呼叫時注入；不重複載入。 |
| R10 | **學術 baseline 被誤改**（live tracking 影響 OOS detail） | OOS detail 路徑與 live 路徑明確區分（OOS 在 image / live 在 volume）；contract test 連 5 次 OOS hash 相同必須綠。 |

## 不在範圍

- GitHub Actions 或其他自動排程（spec 明確標出，純手動觸發）
- PPO 重訓
- 多 policy 並行 live tracking
- 即時 streaming（盤中 tick-level）
- 歷史 prediction 修改（append-only 強制）
- Zeabur 部署具體配置
- Episode 列表分頁
- 多人協作衝突解決
- 修改 reward function / observation shape / env step 邏輯（屬 003 / 008 範圍）
- 修改 009 builder（OOS one-shot，不複用）
- 修改 SMC engine 內部（屬 008 範圍，本 feature 只 import `batch_compute_events`）

## Complexity Tracking

> 無 violation；本區塊留空。
