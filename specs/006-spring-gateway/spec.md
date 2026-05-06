# Feature Specification: Spring Boot API Gateway (C-lite)

**Feature Branch**: `006-spring-gateway`
**Created**: 2026-04-29
**Revised**: 2026-05-06（C-lite 重寫；上一版設計含 Kafka / PostgreSQL / MinIO / JWT，已 SUPERSEDED；保留於 git history `1a17ade`）
**Status**: Draft（C-lite v2）
**Input**: User description: "把 005 PPO Inference Service 包成前端友善的 REST + SSE Gateway。Spring Boot 3.x 一個 service，**不**上 Kafka、**不**上 PostgreSQL、**不**上 JWT。職責只有兩件：(a) 把 /infer/run、/infer/latest、/healthz proxy 給 005，把 snake_case 轉 camelCase + 加 requestId；(b) 訂閱 005 push 到 Redis channel `predictions:latest` 的事件，再以 SSE 廣播給前端 007 戰情室。對應憲法 Principle IV「微服務解耦」中 Java/Spring Boot 一層的最小可行版本。"

## Why C-lite（重寫動機）

論文 demo + 個人 lab 規模（一天 1 個 prediction event）。Kafka / PostgreSQL / MinIO / JWT 全是過度工程：

- **無多租戶**：唯一前端消費者是 007 戰情室；不需要授權系統。
- **無高吞吐**：每天 1 筆 scheduled prediction + 偶爾 manual trigger；Kafka 對這流量是 overkill。
- **無持久化需求**：`predictions:latest` Redis key TTL 7 天 + git commit `prediction_*.json` 已是審稿/論文需要的 source of truth。
- **無長任務**：episode 推理在訓練側已完成（004 / `runs/<id>/eval_in_sample/`），006 不再做 episode runner。
- **部署目標 = Zeabur**：Zeabur 對 docker-compose 友善，但對 Kafka broker 不友善（要付額外 add-on）。

C-lite 範圍 = REST proxy（3 endpoint）+ SSE broadcaster（1 channel）+ healthcheck。整個 Gateway 預期 < 800 行 Java。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 前端統一入口（Priority: P1）

前端工程師需要單一 RESTful 入口，封裝 005 的 Python 內部介面，提供 camelCase JSON、ISO 8601 日期、加上 `requestId`（trace 用）。前端**不**直接呼叫 005，而是統一透過 006 Gateway。

**Why this priority**: 沒有 Gateway 就沒有微服務拓撲；對應憲法 Principle IV 核心。也是前端 007 LivePredictionCard 與 Settings page 手動觸發按鈕的最低限度依賴。

**Independent Test**: 啟動 Gateway（Spring Boot embedded server）、以 `curl POST /api/v1/inference/run` 送請求，驗證 (a) HTTP 200、(b) JSON response 為 camelCase（如 `targetWeights` 而非 005 的 `target_weights`）、(c) Gateway 內部已轉發到 005、(d) response 加上 `requestId`。

**Acceptance Scenarios**:

1. **Given** 005 推理服務運行於內網、Gateway 已配置 `inference.url`，**When** 前端送 `POST /api/v1/inference/run`，**Then** Gateway 轉發給 005 `/infer/run`、收回 `PredictionPayload`、轉換為 camelCase JSON、附上 `requestId` 後回傳。
2. **Given** 005 服務當機，**When** 前端送相同請求，**Then** Gateway 回 HTTP 503 + `{"error": "InferenceServiceUnavailable", "requestId": "..."}`，並在 retry budget（預設 3 次）耗盡後直接 fail-fast。
3. **Given** 前端送 `GET /api/v1/inference/latest`，**When** Redis cache 內有最新 prediction，**Then** Gateway 直接從 005 `/infer/latest` 取得後 camelCase 化回傳。

---

### User Story 2 - SSE 即時廣播（Priority: P1）

戰情室前端 OverviewPage 與 DecisionPage 需要在 005 排程跑出新 prediction 時**即時**收到事件、刷新 LivePredictionCard 與權重圖。前端**不**輪詢 `GET /api/v1/inference/latest`，改以 EventSource 訂閱 `GET /api/v1/predictions/stream`，由 Gateway 中繼 005 push 到 Redis channel `predictions:latest` 的事件。

**Why this priority**: 對應 warroom 架構決策「全頁面 live」與 Principle IV「Redis pub/sub 解耦」；無此設計則前端只能輪詢，UX 與架構皆不過關。也是 007 從 MSW mock 切到真資料的關鍵介面。

**Independent Test**: (a) 起 redis、起 Gateway、用 `redis-cli PUBLISH predictions:latest '<payload-json>'` 模擬 005 push；(b) 用 `curl -N http://localhost:8080/api/v1/predictions/stream` 模擬前端訂閱；(c) 驗證 SSE event `data:` line 含 camelCase 化的 payload；(d) 驗證 Gateway 對 N 個並發 SSE 連線同時廣播（fan-out）。

**Acceptance Scenarios**:

1. **Given** Gateway 已連上 Redis 並訂閱 `predictions:latest` channel，**When** 005 publish 一筆 PredictionPayload JSON，**Then** Gateway 在 100 ms 內 fan-out 至所有開啟的 SSE 連線、event 名稱為 `prediction`、`data:` 為 camelCase JSON。
2. **Given** 前端 EventSource 中途斷線後 30 秒重連，**When** Gateway 收到 reconnect，**Then** 立即送出最新一筆 cached prediction（從 005 `/infer/latest` 取，避免漏掉斷線期間事件）後恢復串流。
3. **Given** Redis 連線中斷，**When** Gateway 嘗試重新訂閱，**Then** 採 exponential backoff（1s, 2s, 4s, 上限 30s）重試；`/actuator/health` 將 redis component 標 DOWN 但不影響 REST proxy 路徑。

---

### User Story 3 - Healthcheck 與 CORS（Priority: P2）

Zeabur / docker-compose 需要標準健康檢查端點；前端從不同 origin（dev `localhost:5173`、prod 自訂 domain）需要 CORS 允許。

**Why this priority**: 部署到 Zeabur 必需；前端整合必需。但對論文核心（C-lite 路線）非阻擋因素，故為 P2。

**Independent Test**: (a) `GET /actuator/health` 回 200 + `{"status":"UP","components":{"inference":{"status":"UP"},"redis":{"status":"UP"}}}`；(b) 從 `http://localhost:5173` 發 `OPTIONS` preflight，驗證 `Access-Control-Allow-Origin` 含該 origin；(c) 005 down 時，health 整體 `status=DOWN` 且 inference component 為 DOWN，但 SSE 路徑仍可訂閱（Redis 仍通）。

**Acceptance Scenarios**:

1. **Given** Gateway 啟動完成、005 與 Redis 都通，**When** 抓取 `/actuator/health`，**Then** 回 200 + status=UP + inference/redis 兩個 component 各自 UP。
2. **Given** 環境變數 `CORS_ALLOWED_ORIGINS=http://localhost:5173,https://warroom.example.com`，**When** 前端從允許 origin 發 OPTIONS preflight，**Then** Gateway 回 `Access-Control-Allow-Origin` 與該 origin 相符。

---

### Edge Cases

- **005 連線超時**：呼叫 005 `/infer/run` 超過 90 秒（含 env warmup）MUST 回 504 + `{"error":"InferenceTimeout"}`；不嘗試重試（上游 005 自身 mutex 已序列化、重試只會堆積）。
- **005 回 409 INFERENCE_BUSY**：MUST 透傳 status code 409 + 原 ErrorResponse（轉 camelCase + 加 requestId），不轉 503（語意不同：busy ≠ unreachable）。
- **Redis 斷線**：MUST 不影響 REST proxy；SSE 連線改回「降級模式」每 30 秒輪詢 005 `/infer/latest`，並送 `event: degraded` 通知前端切到 polling fallback。
- **SSE 客戶端斷線**：MUST 自動清理 emitter、釋放對應 thread；不能 leak 連線。
- **payload 格式錯誤**：Redis channel 收到不是 valid JSON 的訊息 MUST log warning、跳過該訊息、繼續訂閱（不 crash subscriber）。
- **CORS preflight**：MUST 正確處理 `OPTIONS`；若 origin 不在白名單 MUST 回 403。

## Requirements *(mandatory)*

### Functional Requirements

#### REST API（前端入口）

- **FR-001**: 系統 MUST 提供 `POST /api/v1/inference/run`：proxy 至 005 `/infer/run`、回應轉 camelCase、附 `requestId`（UUID v4）；timeout 90 秒。
- **FR-002**: 系統 MUST 提供 `GET /api/v1/inference/latest`：proxy 至 005 `/infer/latest`、回應轉 camelCase、附 `requestId`；timeout 5 秒。
- **FR-003**: 系統 MUST 提供 `GET /api/v1/inference/healthz`：proxy 至 005 `/healthz`，純粹 pass-through 給前端確認 005 自身 status；本端點與 `/actuator/health` 不同（後者是 Gateway 自身健康）。
- **FR-004**: 全部 REST endpoint MUST 採 camelCase JSON、ISO 8601 日期字串；005 回應的 snake_case key（如 `target_weights`、`as_of_date`、`triggered_by`）MUST 轉成 `targetWeights`、`asOfDate`、`triggeredBy`。
- **FR-005**: 錯誤回應 schema 統一為 `{"error": str, "message": str, "requestId": str, "details": object | null}`；HTTP status 對齊 contracts/error-codes.md。

#### SSE 廣播

- **FR-006**: 系統 MUST 提供 `GET /api/v1/predictions/stream`：HTTP GET、`Content-Type: text/event-stream`、支援多並發訂閱；每收到 Redis `predictions:latest` channel 一筆訊息、fan-out 一個 SSE event（`event: prediction`、`data: <camelCase JSON>`）。
- **FR-007**: 系統 MUST 在 SSE 連線建立時立即送一筆最新 cached prediction（從 005 `/infer/latest` 取）作為 initial state，避免前端等下一次 cron 才有資料。
- **FR-008**: 系統 MUST 對 SSE 連線送 keep-alive comment（`:\n\n`）每 15 秒，避免中介 proxy（Zeabur edge / nginx）斷連。
- **FR-009**: 系統 MUST 在 Redis 斷線期間切換到「polling fallback」：每 30 秒從 005 `/infer/latest` 取最新值並 push SSE event；恢復連線後回到 push 模式。

#### 健康檢查與 CORS

- **FR-010**: 系統 MUST 啟用 Spring Boot Actuator `/actuator/health`；health 含兩個自訂 component：`inference`（HTTP probe 005 `/healthz`）、`redis`（連通 + ping）；任一 DOWN 整體 DOWN。
- **FR-011**: 系統 MUST 透過環境變數 `CORS_ALLOWED_ORIGINS`（逗號分隔多 origin）控制 CORS 白名單；對全部 `/api/v1/**` endpoint 套用。
- **FR-012**: 系統 MUST 寫結構化 JSON log（log4j2 或 logback + Jackson）到 stdout；每筆含 `timestamp`、`level`、`logger`、`requestId`、`event`、`durationMs`；錯誤含 `errorClass` 但不洩漏 stack trace（與 005 對齊）。

#### 介面契約

- **FR-013**: 系統 MUST 提供 OpenAPI 3.1 規格檔 `contracts/openapi.yaml`（手寫或由 springdoc-openapi 產生）；前端 007 可由此產生 TypeScript client stub。
- **FR-014**: 系統消費 005 之 OpenAPI 規格（`specs/005-inference-service/contracts/openapi.yaml`）並由其產出 Java client（用 openapi-generator-maven-plugin 或手寫 RestClient）；005 介面變動 MUST 觸發 006 重新產生或同步 client。

#### 部署相關

- **FR-015**: 系統 MUST 提供 `Dockerfile`（多階段 build：maven build → openjdk runtime；JRE 21+）；image size < 300 MB。
- **FR-016**: 系統 MUST 支援透過環境變數覆寫所有外部相依：`INFERENCE_URL`（預設 `http://python-infer:8000`）、`REDIS_URL`（預設 `redis://redis:6379/0`）、`REDIS_CHANNEL`（預設 `predictions:latest`）、`CORS_ALLOWED_ORIGINS`、`SERVER_PORT`（預設 `8080`）。
- **FR-017**: 系統 MUST 提供 `infra/docker-compose.gateway.yml` 起 spring-gw + redis + python-infer 三個 service（python-infer 從 005 image 拉），驗證端對端整合。

#### 不在範圍內

- **FR-018**: 本 feature **不**做：Kafka（C-lite 主體決策）、PostgreSQL / 任何 RDBMS、MinIO / 物件儲存、JWT / 任何 auth、Prometheus 指標（除非 Spring Actuator 預設 endpoint）、rate limiting、熔斷器（005 自身 mutex 已處理 race；額外熔斷器在 1 RPS 級流量無效益）、episode runner、policy 載入/卸載、refresh token、SSO/OAuth2、跨資料中心 replication、CSV 匯出。

### Key Entities

- **PredictionEvent**: SSE 廣播的單一 prediction 事件；payload schema 與 005 `PredictionPayload` 對齊（轉 camelCase 後）。
- **GatewayHealth**: `/actuator/health` 回應；含 inference、redis 兩個 component。
- **ErrorResponse**: 統一錯誤格式 `{error, message, requestId, details}`。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `POST /api/v1/inference/run` 端對端 latency（前端視角）< 005 自身延遲 + 50 ms Gateway overhead；典型情況 p99 < 95 秒（005 inference + warmup ~90s + Gateway ~50ms）。
- **SC-002**: `GET /api/v1/inference/latest` p99 < 100 ms（純 proxy 無業務邏輯）。
- **SC-003**: SSE 廣播 fan-out 延遲 p99 < 100 ms（從 005 publish 到所有 connected client 收到 event）。
- **SC-004**: 005 服務當機時，REST 端點 5 秒內回 503；Redis 斷線時 SSE 端點 30 秒內切到 polling fallback、不 crash。
- **SC-005**: 整合測試覆蓋率 ≥ 75%（不含 framework 自動生成程式碼）；含 testcontainers 跑真實 Redis 的端對端 test。
- **SC-006**: `/actuator/health` 在 005 / Redis 任一 down 時對應 component status=DOWN，整體 status=DOWN。
- **SC-007**: OpenAPI 規格通過 `swagger-cli validate`；由其產出之 TypeScript client（007 用）可成功 build。
- **SC-008**: 本機 `docker compose -f infra/docker-compose.gateway.yml up` 後 60 秒內全部 service ready；`curl localhost:8080/actuator/health` 回 UP。

## Assumptions

- 005 推理服務已實作完成（Phase 7 已 land）、提供穩定 OpenAPI 介面與 `/healthz`；其 Python 內部仍跑 snake_case，由 Gateway 負責 camelCase 轉換。
- Redis 由 005 同 docker-compose 共用（local dev）或 Zeabur managed Redis 提供（prod）。Gateway 自己**不**起 Redis instance。
- 007 React 戰情室為唯一前端消費者；其他 client（mobile app、CLI 工具）不在當前範圍。
- 部署目標：Phase 1 本機 docker-compose、Phase 2 Zeabur app（每 service 一個 Zeabur deployment）；不上 GCP / Render / Cloudflare Tunnel / Kubernetes。
- Spring Boot 版本 3.x（與憲法 Tech Stack 對齊）、Java 21（LTS）；不採用 Kotlin（保持單一 JVM 語言、降低 build 複雜度）。
- 不做認證授權；論文 demo 場景下，Gateway 暴露於受控網路（個人 lab、Zeabur private、或 Cloudflare Access 後）；商業化階段才補 JWT 屬另一 feature。
- 不做指標 / Prometheus；Spring Actuator `/actuator/metrics` 已足以肉眼 debug；論文不需要正式 SRE observability stack。
