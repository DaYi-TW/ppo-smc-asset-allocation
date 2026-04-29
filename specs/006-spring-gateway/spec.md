# Feature Specification: Spring Boot API Gateway

**Feature Branch**: `006-spring-gateway`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 Spring Boot 後端 API Gateway，作為 React 戰情室前端與 Python 推理服務間的中介層；透過 Kafka 解耦推理任務、行情查詢、交易日誌寫入；持久化 episode 推理結果與決策日誌至資料庫，提供 RESTful API 給 007 戰情室消費。對應憲法 Principle IV「微服務解耦」中 Java/Spring Boot 一層。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 統一前端 API 入口（Priority: P1）

前端工程師需要一個穩定的 RESTful API 入口，封裝 005 推理服務之 Python 內部介面，提供前端友善的資料模型（如駝峰式 camelCase JSON、ISO 8601 日期、合理錯誤碼），並隱藏微服務內部拓撲。前端**不**直接呼叫 005，而是統一透過 006 Gateway。

**Why this priority**: 沒有 Gateway 就沒有微服務拓撲；對應憲法 Principle IV 核心。也是前端開發的最低限度依賴。

**Independent Test**: 啟動 Gateway（Spring Boot embedded server）、以 `curl POST /api/v1/inference/infer` 送合法 request，驗證 (a) HTTP 200、(b) JSON response 為 camelCase 命名（如 `policyId`、`logProb` 而非 005 的 `policy_id`、`log_prob`）、(c) Gateway 內部已轉發到 005、(d) Gateway 加上 `requestId`（trace 用）。

**Acceptance Scenarios**:

1. **Given** 005 推理服務運行於內網、Gateway 已配置 `inference.url`，**When** 前端送 `POST /api/v1/inference/infer`，**Then** Gateway 轉發給 005、收回回應、轉換為 camelCase JSON、附上 `requestId` 與 `gatewayLatencyMs` 後回傳。
2. **Given** 005 服務當機，**When** 前端送相同請求，**Then** Gateway 回 HTTP 503 + `{"error": "InferenceServiceUnavailable", "requestId": "..."}`，並於 N 秒內熔斷後續請求避免雪崩。

---

### User Story 2 - Kafka 解耦長任務（Priority: P1）

完整 episode 推理（005 之 `/v1/episode/run` 跑 8 年區間 ~30 秒）若同步 HTTP 處理會阻塞前端與 Gateway 連線；系統 MUST 將其轉為非同步任務：前端送 `POST /api/v1/episode/run`，Gateway 立即回 `{"taskId": "..."}`，將任務丟入 Kafka topic `episode-tasks`，Worker 消費後呼叫 005、結果寫回 Kafka topic `episode-results` 並落地資料庫；前端 polling `GET /api/v1/tasks/<taskId>` 或訂閱 SSE 取得結果。

**Why this priority**: 對應憲法 Principle IV「Kafka 解耦」明文要求；無此設計則架構與憲法不符，且實務上長任務同步處理會無法上 production。

**Independent Test**: 模擬前端送 100 個並發 episode 任務，驗證 (a) 全部立即取得 `taskId`、(b) 不阻塞 Gateway thread pool、(c) 各任務於 < 60 秒內完成（由 Worker 背景處理）、(d) 結果可透過 polling 與 SSE 兩種方式取得。

**Acceptance Scenarios**:

1. **Given** Kafka cluster 運行中、Worker 已啟動，**When** 前端送 `POST /api/v1/episode/run`，**Then** Gateway 在 100 ms 內回 `taskId`，任務於 30–60 秒內完成、結果寫入資料庫並可由 `GET /api/v1/tasks/<taskId>` 取得。
2. **Given** Worker 處理任務時 005 服務暫時不可用，**When** Worker 收到 5xx，**Then** 任務自動重試 3 次、間隔 exponential backoff；3 次後標記為 `failed` 並寫入 `error` 欄位。

---

### User Story 3 - 交易決策日誌持久化（Priority: P2）

論文審稿與監管合規需要完整的決策追溯能力：每筆推理請求、每個 episode 結果、每次 policy 切換 MUST 落地至關聯式資料庫，含時間戳、user_id（若有）、輸入 obs hash、輸出 action、policy_id、metadata。資料庫 schema 為單一 source of truth，可由前端查詢、亦可匯出供論文使用。

**Why this priority**: 沒有日誌則無法回答「2025-06-15 那次大幅度減倉決策的依據是什麼」這類審稿/合規問題；屬論文嚴謹性必需，但相對 P1 可後補實作。

**Independent Test**: 跑 100 次推理、10 次 episode run，驗證 (a) `inference_log` 資料表有 100 列、(b) `episode_log` 資料表有 10 列、每列含 trajectory blob、(c) `GET /api/v1/logs/inferences?from=...&to=...&policyId=...` 可分頁查詢、回傳 JSON 含 cursor 分頁。

**Acceptance Scenarios**:

1. **Given** 已執行 100 次 `/api/v1/inference/infer`，**When** 查詢 `GET /api/v1/logs/inferences?policyId=baseline_seed1`，**Then** 回傳該 policy 之全部紀錄、按 timestamp 降冪排序、每頁 50 筆。
2. **Given** episode 結果落地，**When** 查詢 `GET /api/v1/logs/episodes/<episodeId>`，**Then** 回傳完整 trajectory（壓縮 JSON 或分塊串流）+ summary。

---

### User Story 4 - 健康檢查、監控與認證（Priority: P3）

維運需要 actuator 標準端點（`/actuator/health`、`/actuator/info`、`/actuator/prometheus`）、前端需要簡單的 JWT 認證（從 `Authorization: Bearer <token>` 讀取、驗證簽章）以區別研究者帳號（讀寫）與審查者帳號（唯讀）。

**Why this priority**: 部署到 production 必需，但論文核心不依賴；故為 P3。

**Independent Test**: (a) `/actuator/health` 回 200 + 元件健康（包含 005 連通、Kafka、DB、Redis）；(b) 帶非法 JWT 的請求回 401；(c) 唯讀帳號嘗試 `POST` 回 403；(d) `/actuator/prometheus` 回 micrometer 格式 metrics 含 `http_server_requests_seconds_count`、`kafka_consumer_lag`、`inference_proxy_latency_seconds`。

**Acceptance Scenarios**:

1. **Given** Spring Boot Actuator 已啟用，**When** 抓取 `/actuator/health`，**Then** 回傳 status=UP 且 components 含 inferenceService、kafka、db、redis 各自 status。
2. **Given** 唯讀使用者之 JWT，**When** 嘗試 `POST /api/v1/policies/load`，**Then** 回 403 + `{"error": "InsufficientPermissions"}`。

---

### Edge Cases

- **005 服務超時**：呼叫 005 端點超過 timeout（預設 5 秒同步、60 秒 episode）MUST 回 504 + 錯誤碼，並於下次同 endpoint 失敗時加入熔斷器。
- **Kafka 連線中斷**：Gateway 啟動時無法連 Kafka MUST 在 `/actuator/health` 標 DOWN、但 `/api/v1/inference/infer`（同步路徑）仍可用；非同步 episode 路徑回 503。
- **資料庫連線飽和**：HikariCP pool exhausted MUST 回 503（避免拖垮 Gateway thread）、log 寫明連線池狀態。
- **重複 taskId 提交**：同 `Idempotency-Key` header 的請求 MUST 回相同 taskId（避免重試造成重複任務）。
- **trajectory blob 過大**：episode JSON > 10 MB 時 MUST 改寫入物件儲存（S3-compatible）、資料庫存 URI；前端取結果時透過 redirect 或 streaming。
- **JWT 過期**：MUST 回 401 + `{"error": "TokenExpired"}`；不刷新（refresh token 機制屬另一 feature）。
- **CORS preflight**：MUST 正確處理 `OPTIONS` 請求、允許 007 戰情室的 origin（由 config 白名單控制）。

## Requirements *(mandatory)*

### Functional Requirements

#### REST API（前端入口）

- **FR-001**: 系統 MUST 提供 `POST /api/v1/inference/infer`：接受前端 camelCase JSON、轉換為 005 snake_case、轉發、轉換回應、附 `requestId`（UUID）與 `gatewayLatencyMs` 後回傳。
- **FR-002**: 系統 MUST 提供 `POST /api/v1/episode/run`（非同步）與 `GET /api/v1/episode/run/sync`（同步、僅供 ≤ 1 年區間）兩種模式；前者立即回 `taskId`、後者直接回 episode log。
- **FR-003**: 系統 MUST 提供 `GET /api/v1/tasks/{taskId}` 查詢任務狀態（pending、running、completed、failed）與結果；同提供 `GET /api/v1/tasks/{taskId}/stream` SSE 端點推送進度。
- **FR-004**: 系統 MUST 提供 `GET /api/v1/policies` 代理 005 同名端點、`POST /api/v1/policies/load`、`DELETE /api/v1/policies/{policyId}`（後兩者要求 admin role）。
- **FR-005**: 系統 MUST 提供 `GET /api/v1/logs/inferences`、`GET /api/v1/logs/episodes/{id}` 查詢歷史紀錄；支援 `?from`、`?to`、`?policyId`、`?cursor`、`?limit` 參數。
- **FR-006**: 全部 REST endpoint MUST 採 camelCase JSON、ISO 8601 日期字串、HTTP standard 錯誤碼（400/401/403/404/409/422/429/500/502/503/504）；錯誤回應 schema 統一為 `{"error": str, "message": str, "requestId": str, "details": dict | null}`。

#### Kafka 解耦

- **FR-007**: 系統 MUST 使用 Kafka topic `episode-tasks`（key=taskId、value=任務 JSON）派發長任務；Worker（同 Spring Boot app 內 separate component 或獨立 deployment）消費此 topic、呼叫 005、結果寫入 `episode-results` topic 與資料庫。
- **FR-008**: Kafka producer 設定 MUST 包含 `acks=all`、`enable.idempotence=true`、`retries=3`、`max.in.flight.requests.per.connection=5`，確保 exactly-once 語意。
- **FR-009**: Kafka consumer 設定 MUST 包含 `enable.auto.commit=false`（手動 commit 在資料庫寫入成功後）、`isolation.level=read_committed`、`max.poll.records=10`。
- **FR-010**: 系統 MUST 對 005 失敗的任務做 exponential backoff 重試（1s、4s、16s）；3 次後標記為 `failed` 並寫入 `error_class`、`error_message` 欄位。
- **FR-011**: 系統 MUST 提供 `Idempotency-Key` header 支援；同 key 在 24 小時內回相同 taskId（避免重試造成重複任務）。

#### 資料庫持久化

- **FR-012**: 系統 MUST 維護資料庫 schema 含資料表：`inference_log`（id, request_id, policy_id, observation_hash, action, value, log_prob, deterministic, latency_ms, user_id, created_at）、`episode_log`（id, task_id, policy_id, start_date, end_date, status, summary_json, trajectory_uri, created_at, completed_at, error_class, error_message）、`policy_metadata`（policy_id, policy_path, obs_dim, loaded_at, git_commit, data_hashes_json, final_mean_episode_return）、`audit_log`（user_id, action, target, timestamp）。
- **FR-013**: 系統 MUST 透過 Flyway 或 Liquibase 管理 schema migration；任何 schema 變動 MUST 提供 forward + rollback migration。
- **FR-014**: trajectory JSON > 1 MB 時 MUST 寫入物件儲存（S3-compatible，本地開發可用 MinIO），DB 僅存 URI；< 1 MB 直接存 JSONB 欄位。
- **FR-015**: 系統 MUST 提供 `GET /api/v1/logs/inferences/export` 端點：以 CSV 或 NDJSON 格式批次匯出指定時間範圍之 inference log，便於論文使用。

#### 認證與授權

- **FR-016**: 系統 MUST 支援 JWT Bearer token 認證；JWT signing key 由環境變數 `JWT_SIGNING_KEY` 提供（不 commit 入 repo）。
- **FR-017**: 系統 MUST 定義兩個 role：`researcher`（可呼叫所有讀寫端點）、`reviewer`（僅可讀）；`POST /api/v1/policies/load`、`DELETE /api/v1/policies/{id}` 限 `researcher`。
- **FR-018**: 系統 MUST 對 admin 操作（policy 載入/卸載、設定變更）寫入 `audit_log` 資料表。

#### 健康檢查與可觀測性

- **FR-019**: 系統 MUST 啟用 Spring Boot Actuator，暴露 `/actuator/health`、`/actuator/info`、`/actuator/prometheus`、`/actuator/metrics`；其中 health 必含 components：`inferenceService`（HTTP probe 005 `/healthz`）、`kafka`（broker 連通）、`db`（連線池 + 簡單 query）、`redis`（如有用）。
- **FR-020**: 系統 MUST 暴露 micrometer 指標：`http_server_requests_seconds`（含 path label）、`inference_proxy_latency_seconds{policyId}`、`kafka_consumer_lag{topic}`、`task_queue_size`、`task_completion_seconds{status}`、`db_connection_pool_*`。
- **FR-021**: 系統 MUST 寫結構化 JSON log（log4j2 + Jackson）到 stdout；每筆含 `timestamp`、`level`、`logger`、`requestId`、`userId`（若有）、`event`、`durationMs`；錯誤含 `errorClass`，stack trace 寫於 stderr。

#### 介面契約

- **FR-022**: 系統 MUST 提供 OpenAPI 3.1 規格檔 `contracts/openapi.yaml`，由 springdoc-openapi 自動產生；前端可由此產生 TypeScript client stub。
- **FR-023**: 系統消費 005 之 OpenAPI 規格（`specs/005-inference-service/contracts/openapi.yaml`）並由其產出 Java client（用 openapi-generator-maven-plugin）；005 任何介面變動 MUST 觸發 006 重新產生 client。
- **FR-024**: 對外回應之 episode_log 元素 schema MUST 與 003 `info-schema.json` 對齊（透過 Jackson MixIn 將 snake_case 轉 camelCase 但保留語意）。

#### 部署相關

- **FR-025**: 系統 MUST 提供 `Dockerfile`（多階段 build：maven build → openjdk runtime）與 `docker-compose.yml`（local dev：Gateway + 005 + PostgreSQL + Kafka + MinIO）。
- **FR-026**: 系統 MUST 支援透過環境變數覆寫所有外部服務 URL：`INFERENCE_URL`、`KAFKA_BOOTSTRAP_SERVERS`、`DB_URL`、`OBJECT_STORAGE_URL`、`JWT_SIGNING_KEY`、`CORS_ALLOWED_ORIGINS`。
- **FR-027**: 系統 MUST 在 `application.yaml` 提供 `dev`、`test`、`prod` 三個 profile；test profile 用 H2 in-memory + embedded Kafka（testcontainers）。

#### 不在範圍內

- **FR-028**: 本 feature **不**做：訓練（004）、推理運算（005，僅代理）、前端 UI（007）、refresh token、SSO/OAuth2 提供者（僅消費 JWT）、API rate limiting per user（依賴 ingress / API gateway 處理）、跨資料中心 replication。

### Key Entities

- **InferenceLogEntry**: 一筆推理紀錄；對應 DB `inference_log` 資料表。
- **EpisodeTask**: 非同步 episode 任務；屬性：taskId、status、policyId、time range、created_at、completed_at、result_uri 或 result_json。
- **PolicyMetadataEntry**: Policy 在 Gateway 視角的元資料快取；同步自 005 `/v1/policies`。
- **AuditLogEntry**: 系統管理操作記錄；對應 DB `audit_log` 資料表。
- **JwtPrincipal**: 已驗證之 JWT 主體；含 userId、role、issuedAt、expiresAt。
- **GatewayMetric**: Micrometer 指標；name、tags、value。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `POST /api/v1/inference/infer` 端對端 latency（前端視角）p99 < 100 ms（005 自身 < 50 ms + Gateway overhead < 50 ms）。
- **SC-002**: `POST /api/v1/episode/run` 100 並發任務全部於 60 秒內完成（前提 005 有足夠並發容量）。
- **SC-003**: 005 服務當機時，Gateway 在 5 秒內熔斷、後續同 endpoint 請求 100 ms 內回 503（不再嘗試呼叫 005）。
- **SC-004**: 重複 `Idempotency-Key` 在 24 小時內回相同 taskId、無重複資料庫紀錄。
- **SC-005**: 整合測試覆蓋率 ≥ 80%（不含 framework 內部）；含 testcontainers 跑真實 PostgreSQL + Kafka 的端對端 test。
- **SC-006**: `/actuator/health` 在 Kafka / DB / 005 任一 down 時對應 component status=DOWN，整體 status=DOWN（K8s readiness probe 將失敗、流量切走）。
- **SC-007**: OpenAPI 規格通過 `swagger-cli validate`；由其產出之 TypeScript client（007 用）可成功 build。
- **SC-008**: trajectory blob > 1 MB 自動落地物件儲存、DB 僅存 URI；前端取結果時透過 pre-signed URL 直接從物件儲存下載（不經 Gateway 中繼）。
- **SC-009**: 全部 admin 端點操作於 `audit_log` 資料表留下完整紀錄，可由 `SELECT * FROM audit_log` 直接還原時間軸。

## Assumptions

- 005 推理服務已實作完成、提供穩定 OpenAPI 介面與 `/healthz`、`/readyz`。
- Kafka cluster 由 ops 提供（local dev 用 docker-compose embedded Kafka）；不在本 feature 內安裝 Kafka 自身。
- PostgreSQL 為主資料庫；版本 ≥ 14（支援 JSONB 與 GIN index）；本 feature 不做 sharding / read replica。
- 物件儲存使用 S3-compatible（生產可用 AWS S3、GCS、Azure Blob；local dev 用 MinIO）；介面為標準 S3 API。
- JWT signing key 由外部 secret manager 注入（K8s Secret / Vault）；本 feature 不負責 token 簽發（屬另一 IDP feature）。
- 007 React 戰情室為唯一前端消費者；其他客戶端（如 mobile app）不在當前範圍。
- 部署目標 Kubernetes；JVM heap 設定預設 1 GB、Pod 資源 limits 由 K8s manifest 定義。
- Spring Boot 版本 3.x（與憲法 Tech Stack 對齊）、Java 17+、Kotlin 不採用（保持單一 JVM 語言）。
- Test profile 使用 testcontainers（PostgreSQL + Kafka 容器化）；CI 環境需 Docker daemon。
- 本 feature 不處理 GDPR / 個資合規（系統僅紀錄推理 metadata、無真實使用者個資）。
