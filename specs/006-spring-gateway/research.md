# Research: Spring Boot API Gateway（006-spring-gateway）

Phase 0 決策紀錄。

## R1: Build tool — Maven (vs Gradle)

**Decision**: Maven 3.9。

**Rationale**:

1. **Spring Boot 官方範例為主**：starter parent + bom 機制 Maven 為一等公民、Gradle 為對等支援但社群範例 Maven 略多。
2. **論文 reproducibility**：Maven `pom.xml` 顯式列出全部依賴版本、無 build script 邏輯，比 Gradle Kotlin DSL 易審計。
3. **CI 鏡像穩定**：`maven:3.9-eclipse-temurin-17` 為官方鏡像、廣泛採用。
4. **單一 module 不需 Gradle 增量編譯優勢**：本 feature 規模小（< 50 Java 檔），Gradle build cache 邊際效益低。
5. **多語言 monorepo**：repo 同時有 Python（004/005）、JS（007），Java 採 Maven 不增加學習成本。

**Alternatives considered**:

- **Gradle**：增量 build 快、Kotlin DSL 表達力強，但對本 feature 規模 over-engineering。Reject。

## R2: HTTP client to 005 — RestTemplate (vs WebClient)

**Decision**: 阻塞式 RestTemplate 包在 resilience4j-spring-boot3 的 CircuitBreaker / Retry / TimeLimiter；不採用 reactive WebClient。

**Rationale**:

1. **整體應用為傳統 Servlet stack**：spring-boot-starter-web (Tomcat) 而非 webflux；混用 reactive 增加 mental overhead。
2. **同步代理更簡單**：`POST /api/v1/inference/infer` 為同步轉發，async 必要時透過 CompletableFuture / `@Async`。
3. **resilience4j 對 RestTemplate 包裝成熟**：annotation 風格 `@CircuitBreaker(name="inference")`、`@Retry`、`@TimeLimiter` 開箱即用。
4. **效能足以滿足 SC-001**：100 RPS、p99 < 100 ms 的目標下，RestTemplate + connection pool 完全夠用。

**Alternatives considered**:

- **WebClient (reactive)**：對 SSE 串流支援好，但本 feature SSE 端點僅 task progress 推送（自 DB poll），不需 reactive backpressure。Reject。
- **Apache HttpClient 直接用**：少了 Spring 整合，自行管理 metrics、retry、circuit breaker。Reject。
- **OpenFeign**：宣告式 client 風格優雅，但與 openapi-generator 產出的 client 重複。Reject。

## R3: 005 Java client 生成策略

**Decision**: 在 `pom.xml` 配置 `openapi-generator-maven-plugin`（≥ 7.0，OpenAPI 3.1 支援），於 `generate-sources` phase 從 `${project.basedir}/../../specs/005-inference-service/contracts/openapi.yaml` 產生 Java client 至 `target/generated-sources/openapi/`，generator name 為 `java`、library 為 `resttemplate`（而非 webclient/jersey/native，配合 R2）。

**Rationale**:

1. **跨 repo 路徑**：相對路徑指向 monorepo 內的 005 spec yaml，build 時自動更新；CI 跑 `mvn package` 即驗證 client 可成功 build（FR-023）。
2. **不入 git**：生成檔放 target/，避免 review noise；改 005 spec 後 build 自然 regenerate。
3. **resttemplate library**：與 R2 一致；可注入自訂 `RestTemplate` bean（含 resilience4j 包裝）。

**Alternatives considered**:

- **手寫 005 client**：違反契約優先 + 易與 yaml drift。Reject。
- **預先 generate + commit**：noise 大、難維護。Reject。
- **執行時動態 fetch `/openapi.json` 再 generate**：build 階段需服務啟動、CI 流程脆弱。Reject。

## R4: Kafka 解耦設計 — 同 JVM Worker（vs 獨立 deployment）

**Decision**: Worker 為同 Spring Boot app 內的 `@KafkaListener` component（`EpisodeWorker`）；不拆獨立 deployment；但保留拆分能力（透過 profile / property 開關）。

**Rationale**:

1. **本 feature 範圍簡化**：Research demo 規模 < 50 in-flight task，單 JVM 足夠。
2. **同 JVM 共享 DB connection pool / S3 client**：減少資源浪費、簡化 config。
3. **未來可拆**：Worker 邏輯封裝在 `kafka/` 套件、無共享 controller 狀態；要拆只需新增 `app-worker.yaml` profile 關閉 web 模組、保留 listener。
4. **Kafka topic 為邏輯解耦點**：即使同 JVM、producer / consumer 透過 broker 中介，符合憲法 Principle IV「不行程內共享狀態」（broker 才是中介、非 in-memory queue）。

**Alternatives considered**:

- **獨立 worker deployment**：production-grade、scale 獨立，但本 feature 階段 over-engineering。Reject（標 future TODO）。
- **不用 Kafka，用 in-memory ExecutorService**：違反憲法 Principle IV「Kafka 解耦」明文要求。Reject。

## R5: Kafka exactly-once 策略

**Decision**:

- Producer：`acks=all` + `enable.idempotence=true` + `retries=3` + `max.in.flight.requests.per.connection=5`（FR-008）。
- Consumer：`enable.auto.commit=false`、`isolation.level=read_committed`、`max.poll.records=10`（FR-009）；在 listener 內手動 `acknowledgment.acknowledge()`，**僅**在資料庫 commit 成功後才 commit offset。
- 不採用 Kafka transactions（`transactional.id`）；改採「DB transactional outbox + manual ack」模式。

**Rationale**:

1. **DB 為 source of truth**：episode result 必須先寫 DB（含 trajectory_uri / summary），才能 ack Kafka。若 ack 後 DB 失敗則重複處理會由 idempotency-key 防護。
2. **Producer idempotence 足以防 single-broker dedup**：對 episode-tasks topic 即夠。
3. **Kafka transactions 複雜度**：跨 DB + Kafka 的 XA-like 兩階段成本高，本 feature 規模不需。

**Alternatives considered**:

- **Kafka transactions（read-process-write 模式）**：強保證但延遲增加、運維複雜。Reject。
- **At-least-once + DB-side dedup（unique constraint）**：可行但需在 DB schema 強制唯一 task_id；本方案實際採此路線（idempotency_key 唯一 + episode_log.task_id 唯一）。Accept as actual approach。

## R6: 資料庫 — PostgreSQL JSONB（vs MongoDB）

**Decision**: PostgreSQL 14+ + JSONB 欄位儲存 episode_summary / 小型 trajectory；> 1 MB trajectory 落地 S3。

**Rationale**:

1. **關聯 + 半結構化兼得**：inference_log 與 policy_metadata 為強關聯（FK）、適合 SQL；trajectory 為半結構化但可 JSONB query。
2. **單一 DB 簡化運維**：無需同時跑 PG + Mongo。
3. **JSONB GIN index**：query `episode_summary->>'sharpe_ratio' > 1.0` 可建 index、效能足。
4. **Spring Data JPA / JdbcTemplate 整合**：成熟度遠超 Mongo Spring Data。

**Alternatives considered**:

- **MongoDB 純文件**：適合 trajectory 但對 inference_log 強關聯反而不便。Reject。
- **TimescaleDB（PG extension）**：未來若改 time-series 分析可考慮、現階段 over-engineering。Reject。

## R7: 物件儲存 — S3 SDK v2

**Decision**: AWS SDK for Java 2.x（aws-sdk-s3 v2），透過 endpoint override 對接 MinIO（local dev）或 S3 / GCS / Azure Blob（其皆有 S3 兼容 API）。Pre-signed URL 由 `S3Presigner` 生成、有效期 15 分鐘（前端取 trajectory）。

**Rationale**:

1. **SDK v2 為官方推薦**：v1 已 deprecated。
2. **跨雲兼容**：endpoint override 即可切換。
3. **Pre-signed URL 跳過 Gateway 中繼**：對應 SC-008、減少 Gateway 流量。
4. **獨立 client bean**：方便在 test profile 換 MinIO 或 mock。

**Alternatives considered**:

- **MinIO Java SDK 直接用**：非 S3 兼容外可能失彈性。Reject。
- **Spring Cloud AWS**：abstraction 過厚、對 SDK 版本綁定強。Reject。

## R8: 認證 — JJWT + Spring Security filter（vs Spring Authorization Server）

**Decision**: 採用 jjwt 0.12 解析簽章 + 自訂 `JwtAuthenticationFilter` 注入 Spring Security context；不採用 Spring Authorization Server（IDP）；token 由外部 IDP 簽發（K8s Secret 注入 signing key）。

**Rationale**:

1. **本 feature 不負責簽發 token**（FR 範圍外）。
2. **jjwt 輕量**：僅做 verify + parse claims，避免引入完整 OAuth2 server stack。
3. **role mapping 簡單**：JWT claims 內含 `role: researcher | reviewer` → 對應 Spring Security `GrantedAuthority`。
4. **HMAC SHA-256 簽章**：對 internal 用足夠；signing key 64+ bytes 由 K8s Secret 注入。

**Alternatives considered**:

- **Spring Authorization Server**：適合自建 IDP 但範圍外。Reject。
- **Keycloak adapter**：強大但需另起 Keycloak 實例。Reject。
- **OAuth2 Resource Server (Spring Security)**：可選但需 issuer URI / JWKS endpoint，對 demo 階段 over-spec。Reject (未來可換)。

## R9: OpenAPI 規格產生 — springdoc-openapi 自動產出 + CI dump

**Decision**: 使用 springdoc-openapi-starter-webmvc-ui，啟動時自動掃描 controllers 產生 OpenAPI 3.1 spec；CI 跑 `mvn spring-boot:run` 後 `curl http://localhost:8080/v3/api-docs.yaml > specs/006-spring-gateway/contracts/openapi.yaml` 並 git diff 檢查（drift detection）。

**Rationale**:

1. **與 005 同策略**：dump-and-commit 方便下游 build（007 TS client）不依賴執行中服務。
2. **DTO + annotation 為 source of truth**：`@Schema`、`@Operation` 註解直接寫在 controller / DTO，schema 與 code 一致。
3. **3.1 支援 nullable union**：與 005 yaml 表達能力對齊。

**Alternatives considered**:

- **手寫 yaml**：drift 風險高。Reject。
- **生成靜態 yaml at build time（不需服務啟動）**：springdoc 暫無此模式（雖有 maven plugin 但需 spring-boot-maven-plugin run 階段）。Accept current strategy。

## R10: Idempotency-Key 設計

**Decision**: 客戶端在 `POST /api/v1/episode/run` 加 `Idempotency-Key: <uuid>` header；Gateway 將該 key 與生成之 `taskId` 寫入 `idempotency_keys` 資料表（唯一 constraint on idempotency_key），TTL 24 小時。同 key 在 24 小時內 → 直接回原 taskId。

**Rationale**:

1. **任務重試常見場景**：網路 timeout、客戶端 retry 不應產生重複任務。
2. **DB 強保證**：unique constraint 防雙寫；race condition 由 SELECT ... FOR UPDATE / ON CONFLICT 處理。
3. **TTL 24 小時**：對齊一般 API 慣例（Stripe / GitHub）。

**Alternatives considered**:

- **Redis SET with TTL**：快但需引入 Redis（暫不引入）。Reject for now。
- **僅靠 DB unique constraint on episode_log.task_id**：可，但無法處理 task 尚未寫入 DB 之 race。Reject as sole strategy。

## R11: Controller 命名空間與版本

**Decision**: 全部端點前綴 `/api/v1/`；future v2 走 `/api/v2/` 平行 deploy；舊版 6 個月 deprecation。

**Rationale**:

1. **REST best practice**。
2. **與 actuator `/actuator/*` 命名空間區隔**。
3. **gateway 自身的 OpenAPI yaml 產出 group 設定 `path-pattern: /api/**`**，避免 actuator 端點污染 spec。

## R12: testcontainers 策略

**Decision**: 整合測試（`*IT.java`）統一用 `@Testcontainers` + `PostgreSQLContainer` + `KafkaContainer` + `MinIOContainer`（org.testcontainers:minio）；測試 profile activator 為 `@ActiveProfiles("test")`。CI 環境（GitHub Actions）使用 `--privileged` runner 或 docker-in-docker。

**Rationale**:

1. **真實 Kafka / Postgres 行為**：H2 + embedded kafka 不能完整模擬 ack semantics、JSONB query。
2. **隔離**：每個 IT 共享 container 透過 `@Container` static field（per class）；test 間 DB cleanup 用 Flyway clean + migrate。
3. **CI 鏡像可預下載**：減少首次 pull 時間。

**Alternatives considered**:

- **H2 + EmbeddedKafka**：快但行為差異大。僅留作 unit test slice (`@WebMvcTest`)。Accept hybrid。
- **Real shared dev DB**：違反測試獨立性。Reject。
