# Tasks: Spring Boot API Gateway（006-spring-gateway）

**Branch**: `006-spring-gateway` | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

依 plan.md 之 monorepo + maven module 結構（`services/gateway/`）。所有路徑相對 repo root。

## Phase 1: Setup

- [ ] T001 建立 `services/gateway/` maven project：`pom.xml` 含 spring-boot-starter-parent 3.2.x、Java 17、依賴清單（plan.md Technical Context）
- [ ] T002 設定 `openapi-generator-maven-plugin`（≥ 7.0）於 `generate-sources` phase 從 `../../specs/005-inference-service/contracts/openapi.yaml` 產生 005 Java client（library=resttemplate、target=`target/generated-sources/openapi`）
- [ ] T003 [P] 建立 `services/gateway/Dockerfile`（multi-stage：maven build → eclipse-temurin:17-jre runtime）
- [ ] T004 [P] 建立 `services/gateway/docker-compose.yml`（Gateway + 005 + Postgres + Kafka KRaft + MinIO；參考 quickstart.md）
- [ ] T005 [P] 建立 `application.yaml`（預設 + dev profile）、`application-test.yaml`（H2 + embedded kafka）、`application-prod.yaml` 三個 profile
- [ ] T006 設定 `log4j2.xml` JSON appender（log4j2-jackson）；MDC 包含 requestId、userId
- [ ] T007 加入 `.gitignore`：`target/`、`*.log`、IDE 檔
- [ ] T008 [P] 建立 CI workflow `.github/workflows/gateway-ci.yml`：`mvn verify` + dump OpenAPI spec 後 git diff 檢查（FR-022、R9）

## Phase 2: Foundational (Blocking Prerequisites)

**所有 user stories 共用基礎**

- [ ] T009 實作 `GatewayApplication.java`（Spring Boot main + `@SpringBootApplication` + `@EnableJpaRepositories` + `@EnableKafka`）
- [ ] T010 實作 Flyway migration `V1__init_schema.sql`（5 張表 + index + check constraints；contracts/db-schema.md）
- [ ] T011 實作 entities：`InferenceLog`、`EpisodeLog`、`PolicyMetadataEntry`、`AuditLog`、`IdempotencyKey`（含 `@Entity` annotation、Lombok `@Data`）
- [ ] T012 實作 repositories（Spring Data JPA）：`InferenceLogRepository`、`EpisodeLogRepository`、`PolicyMetadataRepository`、`AuditLogRepository`、`IdempotencyRepository`
- [ ] T013 實作 DTO classes（plan.md §3）：`InferenceRequestDto/ResponseDto`、`EpisodeRequestDto/Response`、`TaskStatusDto`、`PolicyDto`、`ErrorResponseDto` 等；全部 `@JsonNaming(LowerCamelCaseStrategy)`
- [ ] T014 實作 `exceptions/GlobalExceptionHandler.java` (`@ControllerAdvice`)：將自訂例外與 framework 例外統一映射為 ErrorResponseDto + 對應 HTTP status（contracts/error-codes.md）
- [ ] T015 實作 `observability/RequestIdFilter.java`：每請求注入 UUID requestId 至 MDC + response header `X-Request-Id`
- [ ] T016 實作 `observability/MetricsConfig.java`：自訂 micrometer 指標（inference_proxy_latency_seconds、task_completion_seconds、task_queue_size）
- [ ] T017 實作 `security/JwtAuthenticationFilter.java`：解析 Bearer token、驗證簽章、注入 `JwtPrincipal` 至 SecurityContext（FR-016）
- [ ] T018 實作 `config/SecurityConfig.java`：endpoint 權限（actuator public、/api/v1/policies/load 限 ROLE_RESEARCHER）、CORS 白名單（FR-017、edge case CORS）
- [ ] T019 實作 `config/RestTemplateConfig.java`：建立 `RestTemplate` bean 含 connection pool + 5 秒 timeout + resilience4j CircuitBreaker / Retry / TimeLimiter
- [ ] T020 實作 `config/KafkaConfig.java`：producer/consumer factory（contracts/kafka-topics.md 之設定）
- [ ] T021 實作 `config/ObjectStorageConfig.java`：S3Client + S3Presigner bean（aws-sdk-s3 v2）；endpoint override 從 env var
- [ ] T022 實作 `config/OpenApiConfig.java`：springdoc-openapi tag、group、JWT security scheme
- [ ] T023 [P] [Unit] 寫 `tests/unit/SecurityConfigTest.java`、`JwtFilterTest.java`、`GlobalExceptionHandlerTest.java`、`RequestIdFilterTest.java`

## Phase 3: User Story 1 - 統一前端 API 入口（P1）— MVP

**Goal**: `POST /api/v1/inference/infer` 可呼叫、轉換 camelCase ↔ snake_case、含熔斷器、p99 < 100 ms。

**Independent Test**: 啟動 Gateway + WireMock 模擬 005 → curl POST → 200 + camelCase JSON + requestId。

- [ ] T024 [US1] 實作 `services/InferenceProxyService.java`：注入 005 Java client + RestTemplate；包 `@CircuitBreaker(name="inference") @Retry @TimeLimiter`；計算 gatewayLatencyMs
- [ ] T025 [US1] 實作 `controllers/InferenceController.java`：`POST /api/v1/inference/infer`；request validation（@Valid）、轉換 dto → 005 client request、收回後寫 inference_log、轉 response DTO
- [ ] T026 [US1] InferenceController 加 metrics middleware：每筆寫 inference_proxy_latency_seconds Histogram with policyId tag
- [ ] T027 [US1] 實作 `controllers/PolicyController.java` GET 端點：透傳 005 `/v1/policies` → DTO（admin 寫操作留 US3）
- [ ] T028 [P] [US1] [Contract] `contract/OpenApiValidityTest.java`：啟動 Spring Boot 後 fetch `/v3/api-docs.yaml`、用 swagger-cli validate
- [ ] T029 [P] [US1] [Contract] `controllers/InferenceControllerTest.java` (`@WebMvcTest`)：mock InferenceProxyService、驗證 200 / 400 / 503 path
- [ ] T030 [US1] [Integration] `integration/EndToEndInferenceIT.java`：testcontainers (Postgres + Kafka) + WireMock (mock 005) → 完整 200 flow + DB 寫入
- [ ] T031 [US1] [Integration] `integration/CircuitBreakerIT.java`：WireMock 連續回 5xx → circuit OPEN → 後續請求 100ms 內 503（SC-003）
- [ ] T032 [US1] [Integration] `integration/InferenceLatencyIT.java`：100 並發 + warm 後 p99 < 100 ms（SC-001）
- [ ] T033 [US1] [Integration] `integration/InferenceErrorMappingIT.java`：005 回 OBSERVATION_DIM_MISMATCH 400 → Gateway 透傳 400 + 同 error code

**Checkpoint**: US1 完成 → 前端可同步呼叫推理 API。

## Phase 4: User Story 2 - Kafka 解耦長任務（P1）

**Goal**: `POST /api/v1/episode/run` 立即回 taskId、Worker 背景跑 005、結果寫 DB + episode-results topic、`/tasks/{id}` 可查詢。

**Independent Test**: 100 並發 task → 全部 < 100 ms 取 taskId、60 秒內完成；可 polling 與 SSE 取結果。

- [ ] T034 [US2] 實作 `services/IdempotencyService.java`：`getOrCreateTaskId(key, requestHash, userId) -> UUID`；DB unique constraint + ON CONFLICT 處理 race
- [ ] T035 [US2] 實作 `services/EpisodeTaskService.java`：呼叫 IdempotencyService、寫 episode_log status=pending、produce 至 episode-tasks
- [ ] T036 [US2] 實作 `controllers/EpisodeController.java`：`POST /api/v1/episode/run`（async）+ `POST /api/v1/episode/run/sync`（≤ 1 年才允許，否則 413）
- [ ] T037 [US2] 實作 `kafka/EpisodeTaskProducer.java`：thin wrapper 對 KafkaTemplate；標 trace id
- [ ] T038 [US2] 實作 `kafka/EpisodeWorker.java` (`@KafkaListener("episode-tasks", containerFactory="manualAckFactory")`)：拿 task → update status=running → call 005 → 收 trajectory → upload S3 if > 1 MB → update status=completed + summary + uri → produce episode-results → ack
- [ ] T039 [US2] EpisodeWorker 加 exponential backoff 重試 3 次（FR-010）：1s/4s/16s；3 次後 status=failed
- [ ] T040 [US2] 實作 `services/ObjectStorageService.java`：put（gzip + S3）、generatePresignedGet（15 分鐘 expiry）；trajectory 序列化用 Jackson + Snappy/GZIP
- [ ] T041 [US2] 實作 `controllers/TaskController.java`：`GET /api/v1/tasks/{id}` 從 DB 讀 episode_log → TaskStatusDto；含 pre-signed URL（若 trajectory_uri 有值）
- [ ] T042 [US2] 實作 `kafka/EpisodeResultConsumer.java` (`@KafkaListener("episode-results")`)：發佈 SSE event 給 in-memory map of (taskId → SseEmitter)
- [ ] T043 [US2] 實作 `controllers/TaskController.java` SSE 端點 `GET /api/v1/tasks/{id}/stream`：建立 SseEmitter 註冊到 map；client 中斷時 cleanup
- [ ] T044 [US2] 實作 `controllers/LogsController.java` `GET /api/v1/logs/episodes/{id}`：透傳 episode_log row → EpisodeResponseDto；trajectory > 1 MB 改回 trajectoryUrl
- [ ] T045 [P] [US2] [Contract] `controllers/EpisodeControllerTest.java`：mock EpisodeTaskService、驗證 202 + taskId schema
- [ ] T046 [US2] [Integration] `integration/EndToEndEpisodeIT.java`：testcontainers full stack + WireMock mock 005 → POST submit → 等待 status=completed → 驗 DB row + S3 object + episode-results event
- [ ] T047 [US2] [Integration] `integration/IdempotencyIT.java`：同 key 兩次 → 同 taskId（SC-004）；同 key + 不同 body → 409 IDEMPOTENCY_KEY_MISMATCH
- [ ] T048 [US2] [Integration] `integration/EpisodeRetryIT.java`：WireMock 前 2 次 5xx 後成功 → status 最終 completed；3 次 5xx → status=failed
- [ ] T049 [US2] [Integration] `integration/ConcurrentEpisodeIT.java`：100 並發 submit、60 秒內全 completed（SC-002）
- [ ] T050 [US2] [Integration] `integration/SseTaskStreamIT.java`：submit + subscribe SSE → 收到 progress + done

**Checkpoint**: US2 完成 → 戰情室可觸發 long-running episode。

## Phase 5: User Story 3 - 交易決策日誌持久化（P2）

**Goal**: inference / episode 紀錄完整落地、可分頁查詢、可匯出。

**Independent Test**: 跑 100 推理 + 10 episode → DB 各表筆數正確；export endpoint 回正確 NDJSON / CSV。

- [ ] T051 [US3] 實作 `controllers/LogsController.java` `GET /api/v1/logs/inferences`：cursor-based pagination（base64 encoded `(created_at, id)` cursor）；`?from=&to=&policyId=&cursor=&limit=`
- [ ] T052 [US3] 實作 `controllers/LogsController.java` `GET /api/v1/logs/inferences/export`：streaming response（StreamingResponseBody）NDJSON 或 CSV；Postgres COPY 或 fetch-size 串流避免 OOM
- [ ] T053 [US3] 實作 `controllers/PolicyController.java` `POST /v1/policies/load`、`DELETE /v1/policies/{id}`：admin role only；委派 005，收成功後 upsert policy_metadata table；寫 audit_log（FR-018）
- [ ] T054 [US3] 實作 `services/AuditLogService.java`：`record(userId, action, target, details, requestId, result)`
- [ ] T055 [US3] 實作 `controllers/AdminController.java` `GET /api/v1/admin/audit-log`：cursor pagination；admin role only
- [ ] T056 [P] [US3] [Contract] `controllers/LogsControllerTest.java`、`AdminControllerTest.java`
- [ ] T057 [US3] [Integration] `integration/LogsQueryIT.java`：寫 100 inference + query → 回 50 列 + nextCursor → 取下一頁正確
- [ ] T058 [US3] [Integration] `integration/LogsExportIT.java`：export NDJSON 1000 列、parse 每行驗 schema
- [ ] T059 [US3] [Integration] `integration/PolicyAdminIT.java`：load → audit_log 有 POLICY_LOAD row；reviewer 嘗試 load → 403

**Checkpoint**: US3 完成 → 論文審稿可匯出 inference 紀錄。

## Phase 6: User Story 4 - 健康檢查、監控與認證（P3）

**Goal**: production-grade 健康檢查、Prometheus、JWT 完整測試。

**Independent Test**: actuator/health 在依賴 down 時回 503；reviewer 寫操作回 403；prometheus 暴露 5 個自訂指標。

- [ ] T060 [US4] 實作自訂 `HealthIndicator`：`InferenceServiceHealthIndicator`（HTTP probe 005 `/healthz`）、`KafkaHealthIndicator` (admin client describe cluster)、`ObjectStorageHealthIndicator`（HEAD bucket）
- [ ] T061 [US4] 加 micrometer 指標：`kafka_consumer_lag{topic}`（透過 `KafkaListenerEndpointRegistry` + admin client 計算）、`task_queue_size` Gauge（DB query count(*) where status in pending,running）
- [ ] T062 [US4] 結構化 JSON log：每 controller method log 一筆 INFO with event/durationMs/status；log4j2 layout 確保欄位完整（FR-021）
- [ ] T063 [US4] 強化 `JwtAuthenticationFilter`：缺 header → 401 TOKEN_MISSING；簽章錯 → 401 TOKEN_INVALID；過期 → 401 TOKEN_EXPIRED
- [ ] T064 [P] [US4] [Integration] `integration/ActuatorHealthIT.java`：依賴 down 對應 component DOWN（停 005 → inferenceService DOWN；停 kafka → kafka DOWN）
- [ ] T065 [P] [US4] [Integration] `integration/JwtAuthIT.java`：缺 token / 無效 / 過期三種情境
- [ ] T066 [P] [US4] [Integration] `integration/MetricsExportIT.java`：跑 100 推理後 `/actuator/prometheus` 含預期指標 + count 正確

**Checkpoint**: US4 完成 → K8s 可正確 readiness probe + Prometheus 抓 metric。

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T067 補 javadoc + README at `services/gateway/README.md`（含 deploy 步驟、env var 列表）
- [ ] T068 [P] 跑全部 quickstart.md 10 個情境，確認 pass
- [ ] T069 [P] 寫 K8s Helm chart at `services/gateway/helm/`（Deployment、Service、ServiceMonitor、ConfigMap、Secret 範例）
- [ ] T070 [P] 確認測試覆蓋率 ≥ 80%（SC-005）：`mvn jacoco:report` 並設 jacoco-maven-plugin coverage gate
- [ ] T071 [P] 跑 swagger-cli validate `specs/006-spring-gateway/contracts/openapi.yaml`（SC-007）
- [ ] T072 [P] 跑 openapi-generator 從 yaml 生 TS client (`-g typescript-axios`) 確認 build 成功（SC-007）
- [ ] T073 整合 sonarqube / spotbugs static analysis（optional but recommended）
- [ ] T074 Final Constitution Check：對照 plan.md 五大原則，文件化任何後期偏離
- [ ] T075 補完 db migration TTL cleanup `@Scheduled` cron job（idempotency_keys.expires_at）

## Dependencies

```text
Phase 1 Setup        → Phase 2 Foundational
Phase 2 Foundational → Phase 3 (US1) ─┐
                                       ├→ Phase 7 Polish
                       Phase 4 (US2) ──┤
                       Phase 5 (US3) ──┤  (US3 部分依賴 US2 episode_log table，但 entity 已在 Phase 2 建好，只需 query)
                       Phase 6 (US4) ──┘
```

US1 (P1)、US2 (P1) 為 MVP 兩條主軸；US3 (P2)、US4 (P3) 後接。可並行於 Phase 2 完成後。

## Parallel Execution 範例

Phase 2 結束後：

```bash
git worktree add ../gateway-us1 006-spring-gateway && # T024-T033
git worktree add ../gateway-us2 006-spring-gateway && # T034-T050
```

US3、US4 共用 entity / DTO / GlobalExceptionHandler，可在 US2 後接續 sequential 跑。

## Implementation Strategy

**MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1) + Phase 4 (US2) — 完整微服務拓撲就位、戰情室可同時跑 inference 與 episode。

**遞增交付**:
1. **MVP-α (US1)**: 同步推理代理 + 熔斷器 + 健康檢查 → 前端可呼叫
2. **MVP-β (US2)**: Kafka 解耦 + episode async + S3 + SSE → 戰情室可跑 long-running episode
3. **+US3**: 完整日誌 + 匯出 → 論文審稿可追溯
4. **+US4**: production-grade observability → K8s 部署
5. **Polish**: Helm chart + 完整 docs
