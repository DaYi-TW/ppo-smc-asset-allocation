# Tasks: Spring Boot API Gateway (C-lite v2)

**Branch**: `006-spring-gateway` | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

依 plan.md C-lite v2 之 Phase 1~7 拆分。所有路徑相對 repo root。Test-first：每個 implementation task 之前先列對應 test task（RED → GREEN）。每個 task 粒度 ≤ 30 分鐘、可獨立 commit。`[P]` 標記 = parallel-safe（不同檔案、無相依）。

## Phase 1: Project skeleton

- [ ] T001 [P] 建立 `services/gateway/pom.xml`：Spring Boot parent 3.3.5、Java 21、依賴清單（spring-boot-starter-web、spring-boot-starter-data-redis、spring-boot-starter-actuator、springdoc-openapi-starter-webmvc-ui 2.x、jackson-databind、lombok（optional）；測試端 spring-boot-starter-test、wiremock-standalone、testcontainers-redis、testcontainers-junit-jupiter）；spring-boot-maven-plugin layered jar 開啟。
- [ ] T002 [P] 建立 `services/gateway/src/main/java/com/dayitw/warroom/gateway/GatewayApplication.java`：`@SpringBootApplication` entry point；空 main method.
- [ ] T003 [P] 建立 `services/gateway/src/main/resources/application.yaml`：預設配置（server.port=8080、management.endpoints.web.exposure.include=health,info、logging level、redis 與 inference URL 預設值；spring.data.redis.url 從環境變數覆寫）.
- [ ] T004 [P] 建立 `services/gateway/src/main/resources/application-prod.yaml`：Zeabur profile（CORS_ALLOWED_ORIGINS、INFERENCE_URL、REDIS_URL 全從 env 讀；不寫死 host）.
- [ ] T005 寫 `services/gateway/src/test/java/.../GatewayApplicationTests.java`：smoke test `@SpringBootTest` 驗 context loads（RED：尚無 main class 完整時應失敗，T002 後綠）.
- [ ] T006 跑 `cd services/gateway && mvn test`：T005 預期通過、build 完成；commit 「006 P1: project skeleton + smoke test」.

## Phase 2: REST proxy（US1 P1）

### Tests first（RED）

- [ ] T007 [P] [US1] 寫 `controller/InferenceControllerTest.java`：`@WebMvcTest(InferenceController.class)` + WireMock，case：(a) POST /api/v1/inference/run → 200 + camelCase body + requestId header；(b) 005 回 409 → Gateway 透傳 409 InferenceBusy；(c) 005 timeout → 504 InferenceTimeout；(d) 005 connection refused → 503 InferenceServiceUnavailable. 對應 spec FR-001 / FR-005、acceptance scenario US1-2.
- [ ] T008 [P] [US1] 寫 `service/InferenceClientTest.java`：mock RestClient.Builder，case：(a) snake_case 回應正確反序列化成 PredictionPayloadDto；(b) timeout 配置生效（90s for /run、5s for /latest）；(c) IOException → 包裝為 InferenceServiceException.
- [ ] T009 [P] [US1] 寫 `controller/InferenceLatestTest.java`：case：(a) GET /api/v1/inference/latest → 200 transparent；(b) 005 回 404 → Gateway 回 404 PredictionNotReady. 對應 FR-002.
- [ ] T010 [P] [US1] 寫 `controller/InferenceHealthzTest.java`：case：GET /api/v1/inference/healthz → 200 pass-through；005 503 → Gateway 503. 對應 FR-003.
- [ ] T011 [P] [US1] 寫 `exception/GlobalExceptionHandlerTest.java`：case：(a) InferenceServiceException → 503 + ErrorResponseDto；(b) IllegalArgumentException → 400 BadRequest；(c) 任意 RuntimeException → 500 InternalServerError + 不洩漏 stack.

### Implementation（GREEN）

- [ ] T012 [US1] 建立 `dto/PredictionPayloadDto.java` + `dto/ContextDto.java`：record + `@JsonNaming(SnakeCaseStrategy)`，欄位對齊 data-model.md §2.1.
- [ ] T013 [US1] 建立 `dto/ErrorResponseDto.java` + ErrorCode enum：record，對齊 data-model.md §2.2 + contracts/error-codes.md.
- [ ] T014 [US1] 建立 `dto/HealthDto.java`：record，對齊 data-model.md §2.3.
- [ ] T015 [US1] 建立 `config/WebClientConfig.java`：`@Bean RestClient inferenceRestClient`（baseUrl 從 INFERENCE_URL、timeout 90s default、5s for /latest 走 per-call override）.
- [ ] T016 [US1] 建立 `service/InferenceClient.java`：methods runInference()、getLatest()、getHealthz()；wrap RestClient 呼叫，捕捉 ResourceAccessException / RestClientException 包裝成 InferenceServiceException.
- [ ] T017 [US1] 建立 `exception/InferenceServiceException.java` + 子類（InferenceTimeoutException、InferenceBusyException、PredictionNotReadyException）.
- [ ] T018 [US1] 建立 `exception/GlobalExceptionHandler.java`：`@ControllerAdvice` 把 service exception map 成 ResponseEntity<ErrorResponseDto>；要附 requestId（從 MDC 或 request attribute）.
- [ ] T019 [US1] 建立 `controller/InferenceController.java`：3 個 endpoint 路由 + `@RequestMapping("/api/v1/inference")`；用 InferenceClient；每個 request 入口生成 UUID requestId 寫進 MDC.
- [ ] T020 [US1] 跑 `mvn test`：T007~T011 全綠；commit 「006 P2: REST proxy 三 endpoint + 統一錯誤格式」.

## Phase 3: SSE broadcaster（US2 P1）

### Tests first（RED）

- [ ] T021 [P] [US2] 寫 `service/PredictionBroadcasterTest.java`：mock SseEmitter，case：(a) addClient 後 broadcast 一筆 → emitter.send 被呼叫一次；(b) 100 個 emitter fan-out 全部收到；(c) 某 emitter throw IOException → 該 emitter 被移除、其他 emitter 仍正常收到；(d) registerClient 立即送 initial state（從 InferenceClient.getLatest 取）.
- [ ] T022 [P] [US2] 寫 `controller/PredictionStreamControllerTest.java`：`@WebMvcTest`，case：(a) GET /api/v1/predictions/stream 回 200 + Content-Type text/event-stream；(b) 連線立即收到一筆 initial state event；(c) 模擬 broadcast 後客戶端收到第二筆 event.
- [ ] T023 [P] [US2] 寫 `service/PredictionBroadcasterRedisTest.java`：用 testcontainers Redis，case：(a) 啟 broadcaster + redis-cli PUBLISH → onMessage 觸發 broadcast；(b) Redis 斷線 30s → 切到 polling fallback、每 30s 從 InferenceClient.getLatest broadcast；(c) Redis 重連 → 自動 resubscribe.
- [ ] T024 [P] [US2] 寫 `service/PredictionBroadcasterKeepAliveTest.java`：模擬 15s 過去（用 fake clock 或 awaitility），驗 emitter 收到 ping comment（":\n\n"）.
- [ ] T025 [P] [US2] 寫 `service/MalformedPayloadTest.java`：Redis publish 一筆非 JSON 訊息 → broadcaster log warning 但不 crash 訂閱.

### Implementation（GREEN）

- [ ] T026 [US2] 建立 `dto/PredictionEventDto.java`：record（eventType / emittedAtUtc / payload nullable）對齊 data-model.md §2.4.
- [ ] T027 [US2] 建立 `config/RedisConfig.java`：`@Bean RedisMessageListenerContainer`（從 LettuceConnectionFactory），`@Bean ChannelTopic predictionsLatest("predictions:latest")`.
- [ ] T028 [US2] 建立 `service/PredictionBroadcaster.java`：`CopyOnWriteArrayList<SseEmitter>` + addClient/removeClient + broadcast(payload)；註冊為 Redis MessageListener；onMessage 解 JSON 成 PredictionPayloadDto 後 fan-out；解析失敗 log warning 跳過.
- [ ] T029 [US2] 在 PredictionBroadcaster 加 polling fallback：監聽 RedisConnectionFailureException，切到 `@Scheduled(fixedDelay = 30000)` polling 模式；恢復連線後 stop scheduler、resubscribe.
- [ ] T030 [US2] 在 PredictionBroadcaster 加 keep-alive：`@Scheduled(fixedDelay = 15000)` 對所有 emitter 送 `SseEmitter.event().comment("ping")`.
- [ ] T031 [US2] 建立 `controller/PredictionStreamController.java`：GET /api/v1/predictions/stream return SseEmitter；新連線立即 broadcaster.addClient + 從 InferenceClient.getLatest 取一筆送 initial state（FR-007）.
- [ ] T032 [US2] 在 GatewayApplication 加 `@EnableScheduling`（給 polling + keep-alive）.
- [ ] T033 [US2] 跑 `mvn verify`：T021~T025 全綠（T023 / T025 需要 docker daemon）；commit 「006 P3: SSE broadcaster + polling fallback + keep-alive」.

## Phase 4: Healthcheck + CORS（US3 P2）

### Tests first（RED）

- [ ] T034 [P] [US3] 寫 `service/InferenceHealthIndicatorTest.java`：mock RestClient，case：(a) 005 /healthz 200 → UP + details.latencyMs；(b) 005 timeout 2s → DOWN；(c) 005 5xx → DOWN.
- [ ] T035 [P] [US3] 寫 `integration/HealthEndpointIntegrationTest.java`：`@SpringBootTest` + WireMock 005 + testcontainers Redis，case：(a) 全 up → /actuator/health 200 + status=UP + 兩 component UP；(b) 005 down → 503 + status=DOWN + inference DOWN；(c) Redis down → 503 + redis DOWN.
- [ ] T036 [P] [US3] 寫 `config/CorsConfigTest.java`：`@WebMvcTest`，case：(a) OPTIONS /api/v1/inference/run from allowed origin → 200 + Access-Control-Allow-Origin；(b) OPTIONS from disallowed origin → 403；(c) 預設環境變數空 → 接受 localhost:5173 一個（dev fallback）.

### Implementation（GREEN）

- [ ] T037 [US3] 建立 `service/InferenceHealthIndicator.java`：implements HealthIndicator；呼叫 InferenceClient.getHealthz；2s timeout（per-call override）；異常 → DOWN + details.error；正常 → UP + details.url + latencyMs.
- [ ] T038 [US3] 建立 `config/CorsConfig.java`：`@Configuration` + `WebMvcConfigurer`，從 CORS_ALLOWED_ORIGINS 環境變數讀（逗號分隔）；對 `/api/v1/**` 套；allow methods GET POST OPTIONS、allow headers *、credentials false（前端不送 cookie）.
- [ ] T039 [US3] 跑 `mvn verify`：T034~T036 全綠；commit 「006 P4: actuator HealthIndicator + CORS 白名單」.

## Phase 5: Docker + compose

- [ ] T040 [P] 建立 `services/gateway/Dockerfile`：multi-stage（maven:3.9-eclipse-temurin-21 build → eclipse-temurin:21-jre-alpine run）；layered jar copy 順序（dependencies → snapshot-dependencies → spring-boot-loader → application）；HEALTHCHECK 用 curl /actuator/health；non-root user；EXPOSE 8080.
- [ ] T041 [P] 建立 `services/gateway/.dockerignore`：排除 target/、IDE 檔、tests 資料.
- [ ] T042 建立 `infra/docker-compose.gateway.yml`：3 個 service — redis（共用 005 image：redis:7-alpine）、python-infer（build context 指向 005 Dockerfile，args POLICY_RUN_ID required）、spring-gw（build context 指 services/gateway，depends_on python-infer healthy + redis healthy）；env 變數 INFERENCE_URL / REDIS_URL / CORS_ALLOWED_ORIGINS / SERVER_PORT 全寫好.
- [ ] T043 手動驗 `docker compose -f infra/docker-compose.gateway.yml up --build` → 60 秒內全部 ready；curl 三 endpoint + SSE → 全 200/正確；commit 「006 P5: Dockerfile + docker-compose.gateway.yml」.

## Phase 6: OpenAPI contract + observability

### Tests first（RED）

- [ ] T044 [P] 寫 `integration/ContractOpenApiTest.java`：`@SpringBootTest`，case：(a) 啟 app 抓 GET /v3/api-docs；(b) 用 swagger-parser 驗 schema 合法；(c) assert paths 含 4 個 endpoint；(d) assert components.schemas 含 PredictionPayload / ErrorResponse / GatewayHealth.
- [ ] T045 [P] 寫 `integration/SchemaParityTest.java`：load `specs/005-inference-service/contracts/openapi.yaml` + 本 Gateway 動態 OpenAPI；對 PredictionPayload schema 比對欄位數一致（snake/camel 對映表內全 cover）；005 OpenAPI 多欄位時 fail 提示同步.

### Implementation（GREEN）

- [ ] T046 在 `pom.xml` 加 springdoc-openapi-starter-webmvc-ui 2.x；application.yaml 開 `springdoc.api-docs.enabled=true`、`springdoc.swagger-ui.enabled=true`.
- [ ] T047 在每個 controller 加 `@Tag` / `@Operation` / `@ApiResponse` 註解，補完 OpenAPI 自動派生不出的描述（例如 SSE event 格式說明）.
- [ ] T048 跑 `mvn spring-boot:run` → 抓 `curl localhost:8080/v3/api-docs > /tmp/gen.json`；對 diff `specs/006-spring-gateway/contracts/openapi.yaml`；任何結構性差異反映回手寫 yaml（保持人工審閱版本）.
- [ ] T049 建立 `services/gateway/src/main/resources/logback-spring.xml`：JSON encoder（用 logstash-logback-encoder 或自訂 layout）；含 timestamp / level / logger / requestId（從 MDC）/ event / durationMs / errorClass.
- [ ] T050 在 `controller/InferenceController` 加 request 攔截：入口記 startTime、出口寫一筆 JSON log line `event=inference.run.completed durationMs=...`；對應 FR-012.
- [ ] T051 跑 `mvn verify`：T044~T045 全綠；commit 「006 P6: OpenAPI contract + structured JSON log」.

## Phase 7: 測試 + polish

- [ ] T052 [P] 跑 `mvn verify` 並產 jacoco coverage report：`mvn jacoco:report`；目標 ≥ 75%（spec SC-005）；補測試直到達標.
- [ ] T053 [P] 跑 `mvn checkstyle:check`（如有導入 google_checks.xml）或 `mvn spotless:check`：code style 全綠.
- [ ] T054 [P] 在 repo root README.md 加一節「How to run War Room locally (full stack)」（005 + 006 + Redis 三 service docker-compose 起）；指向 quickstart.md Path A.
- [ ] T055 [P] 確認 `swagger-cli validate specs/006-spring-gateway/contracts/openapi.yaml` 通過（spec SC-007）；裝法見 quickstart.md.
- [ ] T056 在 specs/006-spring-gateway/quickstart.md「常見錯誤排除」表逐項實際 reproduce 一次（每症狀至少跑出一次）；修錯處的描述.
- [ ] T057 最終 commit「006 P7 polish: 75% coverage + checkstyle + README + swagger-cli」；確認 `git status` 乾淨、`mvn verify` 全綠.

## Acceptance Criteria（對齊 contracts/openapi.yaml + spec.md）

- **A1（FR-001~005、US1）**：3 個 REST endpoint 端對端 OK，camelCase 回應、requestId 附在 header `X-Request-Id` 與 ErrorResponse body；snake_case → camelCase 轉換覆蓋 PredictionPayload 全 14 個欄位（含 context.*）.
- **A2（FR-006~009、US2）**：SSE 多 client fan-out（≥ 10 並發）；Redis 斷線降級到 polling；keep-alive 15s；malformed payload 不 crash.
- **A3（FR-010~012、US3）**：actuator/health 三狀態（全 up / 005 down / Redis down）正確；CORS 白名單運作；JSON log 含 requestId.
- **A4（FR-013~014）**：OpenAPI 3.1 通過 swagger-cli；對 005 OpenAPI 比對 schema parity 自動跑.
- **A5（FR-015~017）**：Dockerfile image < 300 MB（A target）；docker compose 60s 內 ready（SC-008）.
- **A6（FR-018）**：codebase grep 確認無 Kafka / JPA / JWT / MinIO / Prometheus / Resilience4j 任一字串.

## Out of scope（明文）

- 不排：Kafka producer/consumer、JPA entity / Flyway migration、JWT filter / Spring Security、MinIO client、micrometer custom metrics / Prometheus endpoint、熔斷器（Resilience4j）、episode runner、policy 載入卸載 endpoint、refresh token、SSO / OAuth2、CSV 匯出、rate limiting、跨資料中心 replication.
- 不排：openapi-generator-maven-plugin 自動產 Java client（Phase 6 評估後決定，MVP 手寫 DTO）.
- 不排：GraalVM native image（Phase 7+ 效能優化階段才考慮）.
- 不排：007 React 前端切到真 Gateway URL（屬 task #46）.

## Total task count

- Phase 1: 6 tasks
- Phase 2: 14 tasks（5 test + 8 impl + 1 commit）
- Phase 3: 13 tasks（5 test + 7 impl + 1 commit）
- Phase 4: 6 tasks（3 test + 2 impl + 1 commit）
- Phase 5: 4 tasks
- Phase 6: 8 tasks（2 test + 5 impl + 1 commit）
- Phase 7: 6 tasks
- **Total: 57 tasks**

## Parallel opportunities

- Phase 2 test tasks T007~T011 全 [P]（不同檔案）
- Phase 2 DTO tasks T012~T014 全 [P]
- Phase 3 test tasks T021~T025 全 [P]
- Phase 4 test tasks T034~T036 全 [P]
- Phase 5 Dockerfile / .dockerignore T040~T041 [P]
- Phase 6 contract tests T044~T045 [P]
- Phase 7 polish tasks T052~T055 [P]
