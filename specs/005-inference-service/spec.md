# Feature Specification: 推理服務（Inference Service）

**Feature Branch**: `005-inference-service`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 Python 推理服務（HTTP API），載入 004 訓練好的 PPO policy checkpoint，對外暴露 RESTful 端點供 006 Spring Boot Gateway 消費，包裝成戰情室前端可視化的 episode 推理結果與決策追溯資料。對應憲法 Principle IV「微服務解耦」中 Python AI 引擎一層。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 對外提供 PPO 推理 API（Priority: P1）

後端 Java 工程師需要一個獨立部署的 Python HTTP 服務，給定當下 observation 即回傳 PPO 推理結果（action weights、value estimate、log prob、reward 三項預估）。服務必須能載入 004 產出之 `final_policy.zip`，於 milliseconds 級別回應請求，且請求/回應 schema 為穩定 JSON 契約。

**Why this priority**: 戰情室前端（007）必須透過 006 Gateway 取得 PPO 決策；沒有推理 API，整個微服務鏈路斷裂。對應憲法 Principle IV「微服務解耦」核心。

**Independent Test**: 啟動服務（`uvicorn` 或等效）、以 `curl POST /v1/infer` 送一個合法 observation JSON，驗證 (a) HTTP 200 回應、(b) JSON 含 `action`、`value`、`log_prob`、`reward_components_estimate` 鍵、(c) `action` 為 7 維 simplex（sum=1、各維 ∈ [0, 0.4] 含 cap、cash 不受 cap 限）、(d) p99 延遲 < 50 ms。

**Acceptance Scenarios**:

1. **Given** 服務已啟動並載入 `final_policy.zip`，**When** 送出 003 spec FR-010 規範之 63 維 observation JSON，**Then** 回應之 `action` 為 7 維 float、sum=1、且符合 003 position_cap 限制。
2. **Given** 同上服務，**When** 送出 33 維 observation（include_smc=False 對應），**Then** 服務應依 model metadata 自動偵測 obs 維度、若與 model 期望不符 raise HTTP 400 「Observation dim mismatch」。

---

### User Story 2 - 完整 episode 推理與決策日誌（Priority: P1）

前端戰情室需要一次取得「給定一段歷史資料、用當前 policy 跑完整 episode 的逐步決策軌跡」，包含每步的 weights、NAV、reward 三項分量、SMC 訊號 raw 值，以便繪製可重播的決策動畫。服務必須提供 `POST /v1/episode/run` 端點，接受時間範圍 + policy_id 參數，回傳完整 episode log（JSON array）。

**Why this priority**: 戰情室「PPO 決策回放」是論文視覺化主軸之一；對應憲法 Principle II（特徵可解釋性）的視覺化驗證面向。

**Independent Test**: 送 `POST /v1/episode/run` body `{"policy_id": "<id>", "start_date": "2025-01-01", "end_date": "2025-12-31"}`，驗證回傳 (a) status 200、(b) `episode_log` 為 array 長度 == 該區間有效交易日數、(c) 每筆元素通過 003 `info-schema.json` 驗證（透過 `info_to_json_safe` 序列化）、(d) `episode_summary` 含最終 NAV、最大回撤、Sharpe ratio。

**Acceptance Scenarios**:

1. **Given** 服務已載入 policy，**When** 請求 2025 全年 episode，**Then** 回傳之 trajectory 與直接以 003 `PortfolioEnv` + 同 policy 跑出的結果 byte-identical（SC-002 跨層一致性）。
2. **Given** 同上請求，**When** 另開連線同樣請求，**Then** 兩次回應完全相同（無隨機性、無快取一致性問題）。

---

### User Story 3 - Policy 版本管理與切換（Priority: P2）

研究者訓練了多個 policy（不同 seed、不同 ablation 設定），希望服務能同時持有多個 policy、依請求參數切換，而不需重啟服務。服務必須支援 `GET /v1/policies` 列出已載入 policy 與 metadata、`POST /v1/policies/load` 載入新 policy、`DELETE /v1/policies/<id>` 卸載。

**Why this priority**: 論文 Findings 章節需要前端「切換 policy 比較」的互動體驗；切換不是部署核心需求但顯著提升 demo 價值。

**Independent Test**: (a) `GET /v1/policies` 回傳當前載入清單；(b) `POST /v1/policies/load` body `{"policy_path": "runs/<...>/final_policy.zip", "policy_id": "baseline_seed1"}` 回傳 200 + 新 policy metadata；(c) 之後 `POST /v1/infer` 帶 `policy_id` 參數即可指定推理用 policy。

**Acceptance Scenarios**:

1. **Given** 服務啟動時載入 `baseline_seed1`，**When** 透過 API 載入 `ablation_seed1`，**Then** `GET /v1/policies` 回傳兩筆；推理時可指定 `policy_id` 切換、各自結果一致。
2. **Given** 已載入 5 個 policy，**When** 請求 `DELETE /v1/policies/baseline_seed1`，**Then** 該 policy 從記憶體移除、後續以該 id 推理 raise HTTP 404。

---

### User Story 4 - 健康檢查與可觀測性（Priority: P3）

後端維運與 Spring Boot Gateway 需要標準化的健康檢查端點與 metrics 暴露端點，以對接 Kubernetes liveness/readiness probe 與 Prometheus 抓取。

**Why this priority**: 部署到 production 必需，但論文核心主張不依賴；故為 P3。

**Independent Test**: (a) `GET /healthz` 回 200 + `{"status": "ok"}`；(b) `GET /readyz` 在 policy 尚未載入時回 503、載入後回 200；(c) `GET /metrics` 回 Prometheus exposition format 文字、含至少 `inference_requests_total`、`inference_latency_seconds`、`policies_loaded_count` 三個指標。

**Acceptance Scenarios**:

1. **Given** 服務剛啟動但尚未載入任何 policy，**When** 請求 `/readyz`，**Then** 回 503；當 policy 載入完成後再請求應回 200。
2. **Given** 服務已處理 1000 次推理，**When** 抓取 `/metrics`，**Then** `inference_requests_total` ≥ 1000、`inference_latency_seconds_bucket` 分佈合理。

---

### Edge Cases

- **Policy 檔案損毀**：`POST /v1/policies/load` 指向之 zip 檔損毀或非 stable-baselines3 格式 MUST 回 HTTP 400 + 明確訊息，不得讓服務崩潰。
- **Observation 維度不符**：請求中 `observation` 維度與 policy `obs_dim` 不符 MUST 回 HTTP 400 「Expected dim {N}, got {M}」。
- **NaN observation**：observation 含 NaN MUST 回 HTTP 400（與 003 對齊：上游應 sanitize 後再送、服務不靜默替換）。
- **Concurrent 推理**：服務 MUST 支援同時 100 個並發推理請求（uvicorn workers + thread pool 設定），無資料競爭。
- **大 episode 區間請求**：`POST /v1/episode/run` 區間覆蓋 > 5 年 MUST 串流（chunked response）回應或 reject + 建議分段，避免單次 response > 10 MB。
- **Policy 推理錯誤**：policy.predict() 內部異常 MUST 回 HTTP 500 + `error_id`（UUID）並記入服務 log，回應 body 不洩漏 stack trace。
- **服務啟動時 model 路徑不存在**：MUST 在 `/readyz` 回 503、log 寫明缺檔、但不阻塞 `/healthz`（liveness 應仍回 200，避免被 K8s 重啟陷入無限循環）。

## Requirements *(mandatory)*

### Functional Requirements

#### HTTP API（單機推理）

- **FR-001**: 系統 MUST 提供 `POST /v1/infer`，request body 含 `observation: list[float]`（長度 33 或 63、由 policy metadata 決定）、`policy_id: str | null`（None 用 default policy）、`deterministic: bool = false`；response 含 `action: list[float]`（7 維）、`value: float`（critic 預估）、`log_prob: float`（policy 對 action 的 log prob）、`reward_components_estimate: dict | null`（若 model 包含 reward predictor 則填、否則 null）、`policy_id: str`、`inference_id: str`（UUID 用於追蹤）、`latency_ms: float`。
- **FR-002**: `POST /v1/infer` 之 action MUST 已通過 003 動作處理管線（NaN 檢查、L1 normalize、position cap），即客戶端拿到的 action 直接合法可用、無需自行後處理。
- **FR-003**: 服務 MUST 支援 `deterministic=true/false` 兩模式：true 用 `policy.predict(obs, deterministic=True)`（生產推理），false 用 stochastic sampling（用於 demo 多樣性）。

#### Episode 推理 API

- **FR-004**: 系統 MUST 提供 `POST /v1/episode/run`，request body 含 `policy_id`、`start_date`、`end_date`、`include_smc: bool`、`seed: int | null`，response 含 `episode_log: list[dict]`（每筆通過 003 info-schema.json 驗證）與 `episode_summary: dict`（含 final_nav、peak_nav、max_drawdown、sharpe_ratio、total_return、num_steps）。
- **FR-005**: `POST /v1/episode/run` MUST 內部建構 003 PortfolioEnv 實例、跑完 episode、收集每步 info、轉 JSON-safe（透過 003 `info_to_json_safe`）回傳。其結果 MUST 與直接 import 003 + 004 policy 跑得結果 byte-identical。
- **FR-006**: 系統 MUST 提供 `POST /v1/episode/stream` SSE (Server-Sent Events) 端點，逐步推送 episode 進度（用於前端動畫即時播放），每 N step 推一筆（N 由 query param `step_chunk` 控制、預設 10）。

#### Policy 管理 API

- **FR-007**: 系統 MUST 提供 `GET /v1/policies` 列出已載入 policy 之 metadata（policy_id、obs_dim、loaded_at_utc、policy_path、git_commit_hash、data_hashes、final_mean_episode_return、warnings 來自 004 metadata.json）。
- **FR-008**: 系統 MUST 提供 `POST /v1/policies/load` 動態載入新 policy；body 含 `policy_path`（檔案系統路徑或 S3 URI）、`policy_id`（人類可讀別名）；`policy_id` 重複 raise HTTP 409。
- **FR-009**: 系統 MUST 提供 `DELETE /v1/policies/{policy_id}` 卸載 policy；卸載 default policy 後若無其他 policy 則 `/readyz` 回 503。
- **FR-010**: 服務啟動時 MUST 從 `INFERENCE_DEFAULT_POLICY_PATH` 環境變數或啟動參數載入一個 default policy；無 default policy 時 `/readyz` 回 503 但 `/healthz` 仍回 200。

#### 健康檢查與可觀測性

- **FR-011**: 系統 MUST 提供 `GET /healthz`：永遠回 200 + `{"status": "ok", "uptime_seconds": <int>}`，僅供 K8s liveness probe。
- **FR-012**: 系統 MUST 提供 `GET /readyz`：當至少有一個 policy 成功載入時回 200 + `{"status": "ready", "policies_loaded": <int>}`，否則 503 + `{"status": "no_policy_loaded"}`。
- **FR-013**: 系統 MUST 提供 `GET /metrics`：Prometheus exposition format，含 `inference_requests_total{status,policy_id}` (counter)、`inference_latency_seconds{policy_id}` (histogram)、`episode_requests_total` (counter)、`policies_loaded_count` (gauge)、`process_resident_memory_bytes` (gauge)。
- **FR-014**: 系統 MUST 寫結構化 JSON log 到 stdout，每筆含 `timestamp_utc`、`level`、`event`（如 `inference_completed`、`policy_loaded`、`error`）、`inference_id` (若適用)、`policy_id`、`latency_ms`、`status_code`；錯誤時額外含 `error_id` 與 `error_class` 但**不**含 stack trace（trace 寫在 stderr）。

#### 介面契約

- **FR-015**: 系統 MUST 提供 OpenAPI 3.1 規格檔 `contracts/openapi.yaml`，描述全部端點、request/response schema、錯誤碼；`GET /openapi.json` 端點回傳同內容（FastAPI 自動產出可）。
- **FR-016**: 推理回應之 `episode_log` 元素 schema MUST 與 003 `info-schema.json` 一致（透過 import 對齊、不重複定義）。
- **FR-017**: 服務 MUST 將 `contracts/openapi.yaml` commit 入 repo，作為 006 Spring Boot Gateway 之客戶端 stub generation 來源。

#### 性能與可重現

- **FR-018**: `POST /v1/infer` 之 p99 latency MUST < 50 ms（單機 CPU、warm cache）；p50 < 10 ms。
- **FR-019**: `POST /v1/episode/run` 之 1 年區間（~252 step）端對端 latency MUST < 5 秒。
- **FR-020**: 同 policy_id + 同 observation + `deterministic=true`，兩次推理回應之 action MUST byte-identical（容差 0.0）。
- **FR-021**: 同 policy_id + 同 episode 參數（含 seed），兩次 `POST /v1/episode/run` 之 episode_log MUST byte-identical。

#### 不在範圍內

- **FR-022**: 本 feature **不**做：訓練（屬 004）、Java 後端 Gateway（屬 006）、前端 UI（屬 007）、authentication/authorization（依賴 006 Gateway 處理）、TLS（由 ingress 處理）、跨 region replication、persistent storage（推理服務 stateless）。

### Key Entities

- **InferenceRequest**: 單筆推理請求；含 observation、policy_id、deterministic flag。
- **InferenceResponse**: 單筆推理回應；含 action、value、log_prob、reward_components_estimate、metadata。
- **EpisodeRequest**: 完整 episode 推理請求；含 policy_id、time range、include_smc、seed。
- **EpisodeResponse**: 完整 episode 推理回應；含 trajectory log array 與 summary。
- **PolicyHandle**: 服務記憶體中之 policy 物件；屬性：policy_id、stable-baselines3 PPO instance、obs_dim、metadata（從 004 metadata.json 帶入）、loaded_at_utc。
- **HealthResponse**: 健康檢查回應；含 status、uptime、policies_loaded。
- **Metric**: Prometheus 指標；含 name、type（counter/histogram/gauge）、labels、value。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `POST /v1/infer` p99 latency < 50 ms、p50 < 10 ms（100 並發、單機 CPU、warm policy）。
- **SC-002**: `POST /v1/episode/run` 跑 1 年區間 < 5 秒；跑 8 年（2018–2026）區間 < 30 秒。
- **SC-003**: 服務跑 100 萬次 `/v1/infer` 不發生 memory leak（resident memory 增長 < 50 MB）。
- **SC-004**: 跨層一致性：`POST /v1/episode/run` 結果與直接以 003 + 004 policy 跑出的 trajectory byte-identical（容差 0.0）。
- **SC-005**: 同請求 + deterministic=true 兩次推理回應 byte-identical。
- **SC-006**: 服務在 100 個並發 `/v1/infer` 請求下仍能維持 SC-001 的 latency budget。
- **SC-007**: 整合測試覆蓋率 ≥ 85%（不含 stable-baselines3 內部）。
- **SC-008**: `/healthz` 在服務啟動 < 1 秒內可用；`/readyz` 在 default policy 載入後 < 5 秒內回 200。
- **SC-009**: OpenAPI 規格檔通過 `openapi-spec-validator` 驗證；006 Gateway 從此檔產生之 Java client stub 可成功 build。

## Assumptions

- 004 PPO 訓練 feature 已實作完成、產出標準 `final_policy.zip`（stable-baselines3 格式）與 `metadata.json`。
- 003 PortfolioEnv 已實作完成、`info_to_json_safe` 與 `info-schema.json` 為跨層 schema 來源。
- 002 Parquet 快照於本服務同 host 可讀；雲端部署時透過共享 volume 或 PVC 掛載。
- 推理服務為 stateless：所有 policy 都從本地檔案系統載入、無資料庫依賴。
- 預期同時持有 ≤ 10 個 policy（每個 policy ~5 MB，總計 < 100 MB 記憶體）。
- HTTP framework 採 FastAPI（與 stable-baselines3 / Pydantic 生態相容）；ASGI server uvicorn。
- 不做 token-based authentication；認證由 006 Spring Boot Gateway 處理（內網推理服務假設為 trusted zone）。
- TLS 由 ingress / API gateway 處理；本服務只跑 HTTP。
- 觀測指標走 Prometheus pull 模式；不主動 push 到 metric backend。
- 部署目標為 Kubernetes（K8s liveness/readiness probe 標準對接）；Docker Compose / 裸機亦可，但不是主要場景。
