# Feature Specification: 推理服務（Inference Service）— C-lite 版

**Feature Branch**: `005-inference-service`
**Created**: 2026-04-29
**Last Major Revision**: 2026-05-06 — 重新校準範圍至 C-lite microservices 路線（見下方 Changelog）
**Status**: Draft（已重寫，待 `/speckit.plan` 重新對齊 plan/tasks/contracts）
**Input**: 把 `src/ppo_training/predict.py` 包裝成 HTTP 微服務，每日 cron 自動產出隔日目標權重 + 支援前端手動觸發；結果 publish 到 Redis pub/sub channel 給 006 Spring Gateway 廣播給 007 War Room。

## Changelog

- **2026-05-06 重大重寫**：原 spec（2026-04-29）假設 K8s + Prometheus + 多 policy 動態管理 + episode replay SSE + p99 < 50 ms，過度工程。基於 008 完成後對 PPO 實際需求的校準（單機本地 + 偶爾 demo + 論文使用），改採 C-lite 路線：
  - 觸發改為「每日 scheduled cron + on-demand 重跑」雙模式（不是 inference loop）
  - 部署改為 docker-compose → Zeabur（不是 K8s）
  - 訊息層改為 Redis pub/sub（不是 Prometheus pull）
  - 取消多 policy 動態切換、episode replay、SSE stream（feature 005 範圍縮減）
  - latency budget 從 p99 < 50 ms 放寬到單次 ≤ 90 秒（涵蓋 env warmup ~30 秒）
- 舊版本詳細需求保留在 git history（commit `b0b574b` 之前的 spec.md）。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 每日自動產出隔日目標權重（Priority: P1）

研究者 / 論文 demo 使用者每日美股收盤後、無人工介入下取得 PPO 對隔日開盤的目標配置，並透過 War Room 前端視覺化。背後機制：推理服務內建 scheduler，每日 16:30 ET（台北 05:30）自動跑一次 inference handler，把結果發到 Redis pub/sub channel。

**Why this priority**: 這是整個 War Room 即時情境的核心 — 沒有自動 daily prediction，War Room 只是個歷史回放工具，不是「即時決策面板」。對應論文 §System Architecture「即時推理層」主張，且憲法 V「Spec-First」要求 production behaviour 由 spec 明確定義。

**Independent Test**: 啟動服務後等到（或手動推進）下一次 scheduled trigger；驗證 (a) Redis channel `predictions:latest` 收到一筆 prediction event、(b) Redis key `predictions:latest` 內容是合法 prediction JSON、(c) 服務 stdout log 含 `event=scheduled_inference_completed`、(d) 同一筆結果可透過 `GET /infer/latest` 立即讀回。

**Acceptance Scenarios**:

1. **Given** 服務啟動且 default policy 載入完成，**When** scheduled trigger 觸發，**Then** Redis channel 收到符合 prediction JSON schema 的 event、Redis key 同步寫入、TTL = 7 天。
2. **Given** scheduled inference 失敗（policy 例外、資料缺失等），**When** 觸發發生，**Then** stdout log 寫 `event=scheduled_inference_failed` + error_id，且不影響下一次 scheduled trigger（容錯：單次失敗不停 scheduler）。
3. **Given** 服務剛啟動還未到 scheduled trigger 時間，**When** Redis channel 沒有 publisher，**Then** 訂閱者僅看到「尚無 prediction」狀態（可由 `GET /infer/latest` 回傳空或 404 區分）。

---

### User Story 2 - 前端 / 操作者手動觸發重跑（Priority: P1）

研究者在 War Room 前端 Settings 或 DecisionPage 看到資料更新或 policy 換版，手動點「立即重跑預測」按鈕；服務在合理時間內回傳結果，並同步 publish 到 Redis 讓其他訂閱者也收到。

**Why this priority**: scheduled-only 體驗在 demo 場景太被動 — 研究者改了 policy / 補了資料，要立刻看到新預測，不可能等到隔日。on-demand 與 scheduled 共用同一 inference handler，是 P1 的另一半。

**Independent Test**: `curl -X POST http://localhost:8000/infer/run` 不帶 body；驗證 (a) HTTP 200 + 合法 prediction JSON、(b) 回應時間 ≤ 90 秒、(c) Redis channel 同樣收到該筆 event、(d) 連續觸發兩次回應內容可能不同（因為資料時間推移），但 schema 與 deterministic 性質一致。

**Acceptance Scenarios**:

1. **Given** 服務 ready，**When** 操作者送 `POST /infer/run`，**Then** 回應為 prediction JSON + `triggered_by: "manual"`，同筆 event 也廣播到 Redis channel。
2. **Given** 同一秒內收到 2 個 manual trigger 請求，**When** 兩個請求並發到達，**Then** 服務排隊或互斥處理（不可雙跑），第二個請求的 latency 可能略長但仍 ≤ 90 秒。
3. **Given** scheduled run 正在進行中，**When** 操作者手動觸發，**Then** 系統不啟新一輪、回傳「進行中」狀態 + 當前進度標記（或直接等該輪完成回傳結果，由 plan 階段定）。

---

### User Story 3 - 前端取最新 prediction（Priority: P2）

War Room 前端開啟頁面或 SSE 重連後，需要能從 Redis（透過 006 Gateway）拿到最新一筆 prediction 而不必等下一次推理事件；這支撐 OverviewPage `LivePredictionCard` 首屏載入體驗。

**Why this priority**: P1 的兩個故事已經能 publish 到 Redis；但若沒有 `GET /infer/latest`，新訂閱者會看到空白直到下次 trigger。改善體驗、不是 architecture 必要。

**Independent Test**: scheduled / manual trigger 跑過至少一次後，`curl http://localhost:8000/infer/latest` 必須在 < 200 ms 內回 200 + 完整 prediction JSON；若服務剛啟動尚未產出任何 prediction，回 404 + `{"error": "no_prediction_yet"}`。

**Acceptance Scenarios**:

1. **Given** 至少一次 inference 已完成，**When** `GET /infer/latest`，**Then** 回 200 + 該筆 prediction JSON（同 schema、同內容）。
2. **Given** Redis 中該 key 已過 TTL（> 7 天無新預測），**When** `GET /infer/latest`，**Then** 回 404（避免回過期資料）。

---

### User Story 4 - 服務健康檢查（Priority: P3）

部署平台（docker-compose healthcheck / Zeabur health probe）需要明確 endpoint 知道服務是否活著、是否已準備好接 inference。

**Why this priority**: 部署必需，但邏輯簡單、不是論文核心；放 P3 不阻塞 MVP。

**Independent Test**: `curl http://localhost:8000/healthz` 回 200 + `{"status": "ok"}`；服務剛啟動但 policy 還在載入時，可選擇回 503（讓 platform 等待）或回 200 + ready=false（細節由 plan 決定）。

**Acceptance Scenarios**:

1. **Given** 服務 process 存活，**When** `/healthz`，**Then** 回 200。
2. **Given** policy 載入失敗，**When** `/healthz`，**Then** 回非 200（譬如 503），且 stdout 有清楚錯誤 log。

---

### Edge Cases

- **policy.zip 損毀或缺檔**：服務啟動失敗、stdout 寫明缺檔 / 格式錯，**不**進入無預測狀態跑 schedule（避免每天產 garbage）。
- **資料 (data/raw) 過期**：scheduled run 時若資料最後一個交易日比「昨日 ET」還舊（超過 3 日），inference handler 必須 log warning 但仍照跑（資料新鮮度由上游 002 `update` 子命令負責，不是本 service）。
- **Redis 連線斷線**：publish 失敗時，prediction 結果仍要寫入本地 log + stdout（避免結果遺失）；下次 publish 可重試或等下次 scheduled run。
- **scheduled trigger 與 on-demand 並發**：兩條觸發路徑共用同一 inference handler，必須有 mutex / queue，不可同時跑兩個 env（會搶 random state）。
- **時區處理**：scheduled cron 為 ET 16:30，必須處理 DST 切換（夏令時 / 冬令時的 UTC offset 不同），且容器 OS timezone 不可影響業務時間。
- **prediction JSON schema 漂移**：本 service 輸出 schema 必須與 `runs/<run_id>/prediction_*.json` byte-identical（前端不能因為 service 化重寫 parser）。
- **container 重啟**：服務重啟後立即可用 `GET /infer/latest`（從 Redis 拿，不依賴本地檔案系統）；scheduler 不能重複 fire 同一天的 trigger。

## Requirements *(mandatory)*

### Functional Requirements

#### 推理觸發

- **FR-001**: 系統 MUST 提供 HTTP endpoint 接受 on-demand 推理觸發請求（無 request body 必填欄位），請求成功時 MUST 在 ≤ 90 秒內回傳一筆 prediction JSON。
- **FR-002**: 系統 MUST 內建 scheduler，於每日美股收盤後固定時點（預設 ET 16:30、自動處理 DST）自動觸發一次 inference handler；scheduler MUST 在服務 process 存活期間持續執行，無需外部觸發。
- **FR-003**: scheduled 與 on-demand 兩條路徑 MUST 共用同一 inference handler 實作，且 handler MUST 為互斥執行（同一時刻只允許一次推理跑），第二個並發請求需排隊或回傳「進行中」狀態。

#### 推理輸出與廣播

- **FR-004**: 每次 inference 完成 MUST 將結果 publish 到一個專用的 pub/sub channel（名稱 `predictions:latest` 或同等慣例），讓任意訂閱者（如 006 Gateway）收到通知。
- **FR-005**: 每次 inference 完成 MUST 將最新一筆結果寫入一個可被 `GET` 查詢的快取（key `predictions:latest` 或同等慣例），TTL 7 天，允許新連線者立即取得最近一次 prediction。
- **FR-006**: prediction JSON schema MUST 與 `src/ppo_training/predict.py` 產出之 `prediction_*.json` 完全一致（包含 `as_of_date`, `next_trading_day_target`, `policy_path`, `deterministic`, `target_weights{NVDA,AMD,TSM,MU,GLD,TLT,CASH}`, `weights_capped`, `renormalized`, `context{data_root,include_smc,n_warmup_steps,current_nav_at_as_of}`），額外欄位允許新增（如 `triggered_by`、`inference_id`）但 MUST NOT 改名或刪除既有欄位。
- **FR-007**: 系統 MUST 在 prediction JSON 增加 `triggered_by: "scheduled" | "manual"` 與 `inference_id`（UUID）欄位，方便前端 / 訂閱者區分來源與追蹤。

#### 查詢與健康檢查

- **FR-008**: 系統 MUST 提供 HTTP endpoint 讀取「最新一筆 prediction」，內容直接從 FR-005 的快取讀回；若快取為空（從未產出 / 已過期）MUST 回 404 + 明確錯誤訊息。
- **FR-009**: 系統 MUST 提供健康檢查 endpoint，至少能讓部署平台判斷 process 存活與否；policy 載入失敗時 MUST 以非 200 狀態碼回應。

#### 容錯與可觀測性

- **FR-010**: 單次 scheduled inference 失敗 MUST NOT 停止 scheduler，下一次 trigger 仍須照常執行；失敗事件 MUST 有結構化 log（含 timestamp_utc、event=`scheduled_inference_failed`、error_id、error_class）。
- **FR-011**: pub/sub publish 失敗 MUST NOT 拖累 inference 結果寫入快取；publish 失敗 MUST log 但不視為整體失敗。
- **FR-012**: 系統 MUST 寫結構化 JSON log 到 stdout，每筆含 `timestamp_utc`、`level`、`event`（如 `inference_started`、`inference_completed`、`scheduled_trigger_fired`、`publish_failed`）、`inference_id`、`triggered_by`、`latency_ms`、`status`；錯誤時額外含 `error_id`、`error_class`，stack trace 寫 stderr 不寫 response body。

#### 部署與設定

- **FR-013**: 系統 MUST 可透過環境變數設定關鍵參數：`POLICY_PATH`（policy.zip 路徑）、`DATA_ROOT`（data/raw 目錄）、`REDIS_URL`、`SCHEDULE_CRON`（預設 ET 16:30）、`INCLUDE_SMC`（true/false）。
- **FR-014**: 系統 MUST 能以單一 container 啟動（uvicorn 或同等 ASGI server），無需外部 process manager；scheduler 與 HTTP server MUST 在同一 process / 同一 container。
- **FR-015**: 服務 MUST 提供 docker-compose 範例配置，串接 Redis sidecar，於本機 `docker compose up` 後 90 秒內可處理 `POST /infer/run` 請求。

#### 不在範圍內

- **FR-016**: 本 feature **不**做：訓練（屬 004）、Spring Gateway / SSE 廣播 / JWT 認證（屬 006）、前端整合（屬 007 收尾）、Kafka（明確排除）、Prometheus metrics（不在 MVP）、多 policy 動態切換（policy 換版重 build image）、episode replay endpoint（feature 005 舊版範圍，已移除）、TLS（由 ingress / Zeabur 處理）、authentication（依賴 006）。

### Key Entities

- **PredictionEvent**: 一次 inference 完成後產出的事件 / payload；schema 同 `prediction_*.json` + `triggered_by` + `inference_id`。
- **InferenceTrigger**: 觸發一次推理的事件來源；兩種：`scheduled`（cron）、`manual`（HTTP POST）。
- **PolicyArtifact**: 載入的 stable-baselines3 PPO model；container 啟動時從 `POLICY_PATH` 載入，整個 process 生命週期持有。
- **DataSnapshot**: `DATA_ROOT` 指向的 Parquet 集合；inference 時透過既有 `PortfolioEnv` data loader 載入，本 service 不直接處理 IO。
- **MessageChannel**: pub/sub 通道，用於通知訂閱者「有新 prediction」；payload = PredictionEvent。
- **LatestCache**: TTL key/value 快取，存最新一筆 PredictionEvent，供 `GET /infer/latest` 與新訂閱者初始化用。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 本機 `docker compose up` 後 90 秒內，`curl POST /infer/run` 回 200 + 合法 prediction JSON。
- **SC-002**: scheduled trigger 每日固定觸發一次（誤差 ≤ 1 分鐘），連續 7 天無漏跑（DST 切換日不算）。
- **SC-003**: `GET /infer/latest` 在快取命中時 < 200 ms 回應；快取為空時 < 50 ms 回 404。
- **SC-004**: 任意訂閱者連上 pub/sub channel 後，下一次 inference 完成的 publish event 100% 收到（無丟訊息）。
- **SC-005**: prediction JSON schema 跟 `prediction_*.json` 對 diff，除了 `triggered_by`、`inference_id` 之外完全一致（前端 parser 不需修改）。
- **SC-006**: scheduled inference 失敗一次後，下一次 scheduled trigger 仍能成功跑出結果（容錯驗證）。
- **SC-007**: 同一資料快照 + 同一 policy + `deterministic=true`，scheduled 與 manual 兩次推理產出之 `target_weights` byte-identical（容差 0.0），對齊憲法 I「Reproducibility」。
- **SC-008**: 部署到 Zeabur 後（Phase 2），服務 cold start ≤ 60 秒、`GET /healthz` 回 200。

## Assumptions

- 004 PPO 訓練已完成、產出 `runs/<run_id>/final_policy.zip`；本 service container build 時把指定 policy.zip + `data/raw` 內容 copy 進 image，不做動態 reload。
- 002 data ingestion 已實作 `ppo-smc-data update` 子命令；資料新鮮度由上游維護，本 service 假設 `DATA_ROOT` 已是最新。
- 003 PortfolioEnv 介面穩定、`PortfolioEnvConfig` API 不變；本 service 直接 import `src/portfolio_env` + `src/ppo_training/predict.py`。
- Redis 由部署平台提供（本機 docker-compose sidecar，Zeabur 用 managed Redis）；無 Redis 時服務啟動失敗、不退化成 in-memory 廣播。
- ET 16:30 為合理收盤後跑時間（盤後資料約 30 分鐘內 yfinance 釋出）；DST 切換由 scheduler library（如 APScheduler）處理。
- on-demand 並發兩個請求屬於罕見場景；mutex 排隊不需要 fairness queue，FIFO 即可。
- 認證授權由 006 Spring Gateway 處理；本 service 在 docker-compose 內網假設為 trusted zone（前端不直接打本 service）。
- TLS 由 Zeabur ingress 處理；本 service 只跑 HTTP。
- 部署目標非 K8s，故無 readiness probe 區分 / Prometheus metrics / 多 replica 一致性需求。
- 預期同時持有 1 個 default policy；多 policy 比較屬於 demo 加值功能，本 MVP 不做。
- 一次 inference latency 預期 30~90 秒（涵蓋 env warmup ~30 秒 + step iteration），不需要硬撐 ms 級即時推理。
