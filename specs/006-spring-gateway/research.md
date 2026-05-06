# Research: Spring Boot API Gateway (C-lite v2)

Phase 0 決策紀錄。對齊 spec.md C-lite v2（2026-05-06 revision）。

## R1: Build tool — Maven (vs Gradle)

**Decision**: Maven 3.9（spring-boot-maven-plugin 3.3.x）.

**Rationale**:
- Spring Boot 官方文件範例皆以 Maven 為主，`spring init` CLI 預設產 Maven project；快上手.
- 論文/個人 lab 規模，Gradle 的 Kotlin DSL 與 incremental build 優勢不顯著（單模組、< 1000 LOC）.
- Maven 與 IntelliJ IDEA 整合穩定，不易出現「跑得起 IDE 跑不起 CI」問題.

**Alternatives considered**:
- Gradle Kotlin DSL：build script 更靈活、incremental build 快，但學習曲線陡且本 service 不需要客製化 build 步驟.
- Bazel monorepo：跨 Python + Java 統一 build，但 setup cost 太高、不符 C-lite 主體.

---

## R2: Reactive vs MVC — Spring Web MVC

**Decision**: Spring Web MVC（servlet stack）.

**Rationale**:
- 論文規模 1 ~ 10 RPS，Tomcat 200 thread 預設 pool 完全足夠；reactive 無實質吞吐優勢.
- WebFlux 引入 Project Reactor 學習曲線（Mono / Flux / backpressure），降低後續維護者門檻.
- SSE 在 MVC 下用 `SseEmitter` 已是成熟解，不需要 Flux 才能做 server push.
- testcontainers / WireMock / Mockito 全部以 MVC 為主流範例.

**Alternatives considered**:
- Spring WebFlux：reactive、non-blocking IO，但本 service IO 量極小（每秒最多 1 筆 SSE event 廣播）、收益不抵複雜度.

---

## R3: Redis Java client — Lettuce（spring-data-redis 預設）

**Decision**: Lettuce 6.x（透過 spring-boot-starter-data-redis 帶入）.

**Rationale**:
- Spring Boot 3.x 預設選 Lettuce（vs Jedis），整合零配置.
- Lettuce 為 netty-based、支援 async pub/sub、自動 reconnect、多 thread safe.
- Spring `RedisMessageListenerContainer` 已抽象 listener 註冊，少寫 boilerplate.

**Alternatives considered**:
- Jedis：thread-unsafe（每個 thread 一條連線）、reconnect 需手寫.
- Redisson：feature 多但對只用 pub/sub 來說過大（額外 ~5 MB jar、引入分散式 lock / Map / Queue 等不需要的東西）.

---

## R4: SSE 廣播機制 — SseEmitter + CopyOnWriteArrayList

**Decision**:
- Endpoint return type：`SseEmitter`（Spring 4.2+，Servlet 3.1 async）.
- 註冊邏輯：`PredictionBroadcaster` 持有 `CopyOnWriteArrayList<SseEmitter>`，新 client 連線時 add、`emitter.onCompletion` / `onTimeout` / `onError` 回 callback 時 remove.
- Redis listener 收到 message 時 iterate list 呼叫 `emitter.send(event)`，每個 send 包 try-catch、失敗的 emitter 標記為 dead 等待清理.

**Rationale**:
- `CopyOnWriteArrayList` 對讀多寫少場景（連線 N 次 = 寫 N，廣播 = 讀 ∞）合適；fan-out 期間不會被 register/unregister 阻塞.
- Spring 內建 Tomcat async handler 已處理 long-poll / chunked encoding；不需要動 Servlet 配置.

**Alternatives considered**:
- WebSocket（STOMP）：bi-directional 但 SSE 已足夠（前端只訂閱、不發送）；STOMP 增加 frame format 複雜度.
- SseEmitter + `ConcurrentLinkedQueue`：iterate 順序不穩定、且不支援 indexed remove；`CopyOnWriteArrayList` 更直觀.
- Reactor Flux<ServerSentEvent>：需要 WebFlux，與 R2 衝突.

---

## R5: snake_case ↔ camelCase 轉換策略

**Decision**: Jackson `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)` 加在 DTO，輸入時自動把 005 snake_case 反序列化成 Java camelCase 欄位；輸出（給前端）走 Jackson 預設 camelCase 序列化.

**Rationale**:
- 單一處設定（每個 DTO 加一行 annotation），無需手寫 ObjectMapper bean.
- DTO 的 Java 欄位名遵循 Java naming convention（camelCase），符合 IDE auto-complete 與 IntelliJ inspections.
- 對於完全相同的 key（如 `deterministic`）轉換不變，不會誤改.

**Alternatives considered**:
- 全域 `ObjectMapper` config 把 `PROPERTY_NAMING_STRATEGY` 設成 SNAKE_CASE：影響面太大，連 Gateway 自身 ErrorResponse / Health DTO 也會被反向轉，反而要每個輸出 DTO 都手動 override.
- 手寫 MapStruct mapper：過度工程，DTO < 30 欄位.

---

## R6: 對 005 的 client — Spring `RestClient`（vs WebClient / OpenFeign / openapi-gen）

**Decision**: Spring 6.1 內建的 `RestClient`（synchronous，blocking）.

**Rationale**:
- Spring Web MVC stack 用 `RestClient` 一致（不混 reactive）.
- API 比舊 `RestTemplate` 流暢（fluent builder）；自動把 Jackson serialization wired.
- 對 005 呼叫量小（< 1 QPS），blocking IO 無瓶頸.

**Alternatives considered**:
- WebClient：reactive，與 R2 衝突.
- OpenFeign：宣告式 client、簡潔，但要額外引入 spring-cloud-starter-openfeign（拉一坨 spring-cloud BOM、版本鎖定痛苦）.
- openapi-generator-maven-plugin gen Java client：DTO 自動產、版本控管難（每次 005 改要重 build）；Phase 6 評估後決定，MVP 先 RestClient + 手寫 DTO（< 30 欄位）.

---

## R7: 測試策略 — JUnit 5 + WireMock + testcontainers

**Decision**:
- **Unit**：JUnit 5 + Mockito（service / config layer）.
- **Controller**：`@WebMvcTest` + WireMock（mock 005 HTTP）.
- **Integration**：`@SpringBootTest` + testcontainers Redis + WireMock 005，端對端 SSE / REST / health 一次跑.

**Rationale**:
- WireMock 為 Java 生態 mock HTTP server 標準；可錄製 005 真實回應作為 fixture.
- testcontainers 提供 ephemeral Redis container，不污染 host；CI（Docker daemon required）/ local（Docker Desktop）都能跑.
- 整合測試 cover spec FR-001 ~ FR-018 主要場景；單元測試 cover edge cases（CORS preflight、404、CORS 拒絕、CORS allow）.

**Alternatives considered**:
- embedded redis（it.ozimov:embedded-redis）：unmaintained、與 macOS arm64 不相容.
- fakeredis / redis-mock：無 Java 版本.

---

## R8: 部署 image 大小目標

**Decision**: Multi-stage Dockerfile：`maven:3.9-eclipse-temurin-21` 階段 build → `eclipse-temurin:21-jre-alpine` 階段 run；`pom.xml` 加 spring-boot-maven-plugin layered jar；image size 目標 < 250 MB.

**Rationale**:
- alpine JRE base ~80 MB；Spring Boot fat jar ~50 MB；總計 ~130 MB 達標.
- layered jar（`<layers><enabled>true</enabled></layers>`）讓 Docker layer cache 對「依賴不變、code 改」的 build 快.

**Alternatives considered**:
- GraalVM native image：image < 80 MB、冷啟 < 100 ms，但 build 時間 5+ 分鐘、reflection / proxy 配置麻煩；Phase 7 後才評估（屬效能優化、非 MVP）.
- distroless base：image 更小、攻擊面小，但 troubleshoot（無 shell）較痛；Zeabur 場景不需要極致安全.

---

## R9: OpenAPI 產生 vs 手寫

**Decision**: springdoc-openapi 2.x 自動產生 + 一次性 export 為靜態 `contracts/openapi.yaml`（C-lite 重生，Phase 6 任務）；前端 007 從靜態檔產 TypeScript client.

**Rationale**:
- springdoc 從 controller annotation + DTO schema 自動派生 spec；零維護成本.
- 靜態 export 解決「服務未跑時也能讀 spec」需求，便於 PR review.

**Alternatives considered**:
- 純手寫 yaml：每次 controller 改要同步改 yaml，易漂移.
- 純動態（不 export）：無法版本控管 spec，前端 client gen 流程依賴 Gateway 跑著.

---

## R10: 觀測性深度 — 只用 Spring Actuator 預設

**Decision**: 啟用 `/actuator/health`、`/actuator/info`；**不**啟用 `/actuator/prometheus`、micrometer custom metrics、distributed tracing（Sleuth/Zipkin）.

**Rationale**:
- 論文 demo + 個人 lab 規模，Prometheus / Grafana stack 過度工程.
- 結構化 JSON log（FR-012）已足以肉眼 debug；Zeabur 自帶 log streaming UI.
- 商業化 / SLA 階段才需要正式 SRE observability，屬另一 feature 範疇.

**Alternatives considered**:
- micrometer + Prometheus：見上理由排除.
- OpenTelemetry：cross-service trace 對 3 service 拓撲有用，但需要 collector / Tempo / Jaeger 之一，部署複雜度大幅上升.
