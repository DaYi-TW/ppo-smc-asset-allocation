# Implementation Plan: Spring Boot API Gateway (C-lite)

**Branch**: `006-spring-gateway` | **Date**: 2026-05-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-spring-gateway/spec.md`（C-lite v2，2026-05-06 revision）

## Summary

Spring Boot 3.x + Java 21 API Gateway，職責限縮為兩件：(a) **REST proxy** —— 把 005 推理服務的 `/infer/run`、`/infer/latest`、`/healthz` 三個 endpoint 包裝為前端友善的 `/api/v1/inference/*`（snake_case → camelCase + requestId）；(b) **SSE broadcaster** —— 訂閱 005 push 到 Redis channel `predictions:latest` 的事件，以 `GET /api/v1/predictions/stream` 廣播給 007 戰情室前端。**不**做 Kafka、PostgreSQL、MinIO、JWT、episode runner、policy 載入。整個 Gateway 預估 < 800 行 Java；本機 docker-compose 跑通，Phase 2 上 Zeabur 一個 app。技術選型：Spring Boot 3.3、Spring Web MVC（不上 WebFlux：論文規模 1 RPS 不需 reactive）、Lettuce（Redis Java client，async pub/sub support good）、Spring Web 內建 `RestClient`（呼叫 005）、Spring `SseEmitter`（fan-out broadcaster）、Spring Actuator + 自訂 HealthIndicator、testcontainers Redis。

## Technical Context

**Language/Version**: Java 21（LTS）
**Primary Dependencies**: Spring Boot 3.3+, Spring Web (MVC), Spring Boot Actuator, spring-data-redis (Lettuce), springdoc-openapi 2.x, jackson-databind（snake_case ↔ camelCase via `PropertyNamingStrategies`）
**Storage**: 無（stateless proxy；Redis 由 005 共用、Gateway 僅讀）
**Testing**: JUnit 5 + Spring Boot Test + Mockito + WireMock（mock 005 HTTP）+ testcontainers（Redis 端對端整合）
**Target Platform**: Linux container（Phase 1 docker-compose、Phase 2 Zeabur app）；JRE 21 alpine slim
**Project Type**: Web service（單 service、多 endpoint）
**Performance Goals**: REST proxy p99 < 100 ms（純 IO bound、Gateway overhead < 50 ms）；SSE fan-out p99 < 100 ms；單實例支援 ≥ 100 並發 SSE 連線（論文 demo 規模綽綽有餘）
**Constraints**: image size < 300 MB；冷啟到 ready < 30 秒；JVM heap 預設 512 MB（Zeabur free tier 友善）；不引入 Kafka / RDBMS / 物件儲存任何相依
**Scale/Scope**: 1 個 service、~12 個 Java class、3 個 REST endpoint + 1 個 SSE endpoint、~800 LOC（含測試 ~1500 LOC）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` v1.1.0 五原則展開為本 feature gate items。

### Principle I — Reproducibility（NON-NEGOTIABLE）

- **G-I-1**: Gateway 自身為 stateless proxy，不引入新的隨機性或 wall-clock 依賴；`requestId` 用 `UUID.randomUUID()`，但僅作 trace 用途、不影響業務輸出。
- **G-I-2**: Maven `pom.xml` MUST 鎖定 Spring Boot patch 版本（如 `3.3.5`，不用 `3.3+`）；docker image build 時 MUST 鎖定 base image digest（`eclipse-temurin:21-jre-alpine@sha256:...`）。
- **G-I-3**: Gateway 不轉換 005 PredictionPayload 的 numerical 欄位（target_weights 等浮點數一字不漏 pass-through），僅做 key naming 轉換，確保 byte-identical（SC-007 對 005 的承諾延伸到 Gateway）。

### Principle II — Explainability

- **G-II-1**: 結構化 JSON log（FR-012）每筆 request 含 `requestId`、`event`、`durationMs`，前端 trace ID 可貫穿到 005 stderr / scheduler log（005 已有 `inference_id`，Gateway 將其作為 SSE event 的 correlation key）.
- **G-II-2**: OpenAPI 3.1 由 springdoc 自動產生 + 手寫補述，每個 endpoint 註明所代理的 005 端點，論文附錄可直接引用。

### Principle III — Risk-First Reward（NON-NEGOTIABLE）

- **G-III-1**: 本 service **不**改 reward function（屬 003 範疇）；Gateway 僅消費 005 的 `target_weights` 結果，無業務邏輯介入。
- **G-III-2**: Gateway 不對 005 回應做任何後處理（不做 weight rounding / capping / 二次 normalization），保留 005 的 audit trail（`weights_capped`、`renormalized` 欄位透傳到前端）。

### Principle IV — Service Decoupling

- **G-IV-1**: Gateway 對 005 採 HTTP `RestClient`（無共享進程記憶體、無共享 JVM class loader）；005 變動 image 重 build、Gateway 端只需重建 OpenAPI client 或手調 DTO 欄位。
- **G-IV-2**: Gateway 與 Redis 解耦：Redis 斷線 SSE 端點降級到 polling fallback（FR-009），REST 路徑完全不受影響；Redis 重連走 Lettuce 內建 reconnect。
- **G-IV-3**: 不引入 Kafka（warroom 架構決策 2026-05-06）；不引入 RDBMS（C-lite 主體）。

### Principle V — Spec-First（NON-NEGOTIABLE）

- **G-V-1**: 所有 endpoint 行為由 spec FR-001 ~ FR-018 + contracts/openapi.yaml（C-lite 重生版）定義；implementation 期間若發現 spec 不足，先改 spec + commit、再改 code，禁止「實作時加 endpoint」.
- **G-V-2**: contract test（測 OpenAPI schema validity + 對 005 的 client schema parity）為 Phase 7 必交付項，CI 失敗 = block merge.
- **G-V-3**: Out of scope 列表（spec FR-018）為硬約束；implementation 期間若 PR review 發現「順手加了 metric / 加了 cache / 加了 retry queue」MUST reject、回去改 spec 並重走 plan→tasks 流程.

**Gate result**: ✅ 全部 5 原則 gate 滿足；無 violation 需要進 Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/006-spring-gateway/
├── plan.md              # 本檔（C-lite v2）
├── research.md          # Phase 0 決策（C-lite 重生）
├── data-model.md        # Phase 1（DTO only，無 entity）
├── quickstart.md        # Phase 1（docker-compose 5 分鐘起）
├── contracts/
│   ├── openapi.yaml     # C-lite OpenAPI 3.1（待重生；舊版有 SUPERSEDED banner）
│   ├── error-codes.md   # 部分可重用（C-lite 仍需 ErrorResponse 字典）
│   ├── db-schema.md     # SUPERSEDED
│   └── kafka-topics.md  # SUPERSEDED
└── tasks.md             # Phase 2（C-lite 重生；舊版有 SUPERSEDED banner）
```

### Source Code (repository root)

```text
services/gateway/                          # 新增 — 對應憲法 Tech Stack §微服務分層
├── pom.xml                                # Maven build；Spring Boot parent 3.3.5
├── src/main/java/com/dayitw/warroom/gateway/
│   ├── GatewayApplication.java            # @SpringBootApplication entry point
│   ├── config/
│   │   ├── WebClientConfig.java           # RestClient bean（指向 INFERENCE_URL）
│   │   ├── RedisConfig.java               # Lettuce ConnectionFactory + ReactiveRedisTemplate
│   │   ├── CorsConfig.java                # @CrossOrigin 全域配置（FR-011）
│   │   └── JacksonConfig.java             # PropertyNamingStrategy=SNAKE_CASE for in，camelCase for out
│   ├── controller/
│   │   ├── InferenceController.java       # POST /api/v1/inference/run、GET /latest、/healthz
│   │   └── PredictionStreamController.java# GET /api/v1/predictions/stream（SseEmitter）
│   ├── service/
│   │   ├── InferenceClient.java           # 呼叫 005 的 RestClient wrapper
│   │   ├── PredictionBroadcaster.java     # 訂閱 Redis channel → fan-out SseEmitter list
│   │   └── HealthCheckService.java        # 自訂 inference / redis HealthIndicator
│   ├── dto/
│   │   ├── PredictionPayloadDto.java      # camelCase；Jackson MixIn 對齊 005 schema
│   │   ├── ErrorResponseDto.java          # {error, message, requestId, details}
│   │   └── HealthDto.java                 # /api/v1/inference/healthz 回應
│   └── exception/
│       ├── InferenceServiceException.java # 005 unreachable / timeout
│       └── GlobalExceptionHandler.java    # @ControllerAdvice 統一錯誤格式
├── src/main/resources/
│   ├── application.yaml                   # 預設配置（dev profile）
│   ├── application-prod.yaml              # Zeabur profile（從環境變數讀）
│   └── logback-spring.xml                 # JSON log 格式（FR-012）
├── src/test/java/com/dayitw/warroom/gateway/
│   ├── controller/
│   │   ├── InferenceControllerTest.java       # @WebMvcTest + WireMock（mock 005）
│   │   └── PredictionStreamControllerTest.java# SseEmitter 測試 + fakeredis or testcontainers
│   ├── service/
│   │   ├── InferenceClientTest.java
│   │   ├── PredictionBroadcasterTest.java
│   │   └── HealthCheckServiceTest.java
│   ├── integration/
│   │   ├── EndToEndIntegrationTest.java   # @SpringBootTest + testcontainers Redis + WireMock 005
│   │   └── ContractOpenApiTest.java       # 啟 app、抓 /v3/api-docs、用 swagger-parser 驗 schema
│   └── GatewayApplicationTests.java       # Smoke test：context loads
└── Dockerfile                              # 多階段 build：maven → JRE 21 alpine

infra/
└── docker-compose.gateway.yml              # 新增 — spring-gw + python-infer + redis 三 service
```

**Structure Decision**: 新增 `services/gateway/` 目錄為 Maven 單模組 Spring Boot project，與 repo root 的 Python `src/` 並列；不採 monorepo build tool（如 Bazel）—— Spring Boot 自帶的 maven plugin + Python `pyproject.toml` 各自獨立、CI 中分兩個 job 跑（後續 feature 008+ 若需要可再考慮多模組 maven）。`infra/` 目錄已有 `Dockerfile.inference` + `docker-compose.inference.yml`（005 落地），006 加 `docker-compose.gateway.yml`，與 005 docker-compose 共用 redis service。

## Phase Order

依 spec User Story 優先順序 + 內部相依：

- **Phase 1: Project skeleton**（pom.xml + Spring Boot init + healthz smoke）— 對應 setup，無 user story 直接綁定。
- **Phase 2: REST proxy（US1 P1）** — InferenceController + InferenceClient + DTO 雙向轉換 + GlobalExceptionHandler。Gate：US1 端對端可從 curl POST /api/v1/inference/run 透過 WireMock 拿到 camelCase 回應.
- **Phase 3: SSE broadcaster（US2 P1）** — PredictionStreamController + PredictionBroadcaster + Lettuce subscriber。Gate：手動 redis-cli PUBLISH → curl -N 訂閱端收到 event；多 client 並發 fan-out OK.
- **Phase 4: Healthcheck + CORS（US3 P2）** — HealthCheckService（自訂 indicators）+ CorsConfig。Gate：/actuator/health 三狀態正確（005 down / Redis down / 全 up）；不同 origin OPTIONS preflight 行為正確.
- **Phase 5: Docker + compose** — `services/gateway/Dockerfile`（多階段 build）+ `infra/docker-compose.gateway.yml`（spring-gw + python-infer + redis）。Gate：本機 docker compose up → curl 三 endpoint 成功.
- **Phase 6: OpenAPI contract + observability** — springdoc-openapi 開啟、手寫 contracts/openapi.yaml C-lite 版本（用 springdoc 產的當 baseline）；JSON log（logback-spring.xml）。Gate：swagger-cli validate 過、actuator/health 含正確 components.
- **Phase 7: 測試 + polish** — JUnit + WireMock + testcontainers 整合測；coverage ≥ 75%；Maven build clean、checkstyle / spotbugs（如有導入）綠.

**Out of scope**（明文，spec FR-018）：Kafka / RDBMS / MinIO / JWT / Prometheus / rate limiting / 熔斷器 / episode runner / policy 載入卸載 / refresh token / SSO / 跨資料中心 replication / CSV 匯出.

## Risks

- **R1: SSE 在 Spring MVC 的 thread model 限制**
  - **症狀**：SseEmitter 預設用 Tomcat thread pool；100 並發 SSE 連線會吃滿預設 200 thread.
  - **緩解**：論文 demo 規模 1 ~ 10 並發，預設 thread pool 綽綽有餘；若實測壓力測 > 50 時改用 `WebMvcConfigurer.configureAsyncSupport` 切自訂 thread pool（Phase 7 測試時驗證）；或改 WebFlux 但會引入 reactive 學習曲線（C-lite 主體決策不採）.

- **R2: Lettuce pub/sub Listener 語意（不是 reactive）**
  - **症狀**：Spring Data Redis `RedisMessageListenerContainer` 以 dedicated thread 跑 listener，message 處理慢會 block 整 channel.
  - **緩解**：listener 內只做 deserialize + emitter.send，不做 IO；fan-out 用 `Collections.synchronizedList<SseEmitter>` 或 `CopyOnWriteArrayList`，O(N) 廣播但 N < 100 沒問題.

- **R3: snake_case ↔ camelCase 轉換漂移**
  - **症狀**：005 schema 演進（如 008 / future feature）新增欄位時，DTO 缺欄位 → 前端拿不到.
  - **緩解**：`@JsonAnySetter` + 對應 getter 把未知欄位透傳；契約測（Phase 7）每次 005 OpenAPI 更新時跑 schema parity test catch 漂移；OpenAPI gen Java client（FR-014）若選 maven plugin 自動派生 DTO 是更穩做法（評估 Phase 6 決定）.

- **R4: Redis 斷線 + reconnect 期間訊息丟失**
  - **症狀**：Redis pub/sub 不持久化；listener 斷線期間的 publish 永久遺失.
  - **緩解**：FR-007 + FR-009 — SSE 連線初始狀態從 005 `/infer/latest` 取（補回最新一筆）；Redis 斷線時切 polling fallback 每 30s 抓 `/infer/latest`；論文規模一天 1 筆 prediction、漏 1 筆事件不影響 demo（前端會在下次 cron 補回）.

- **R5: Zeabur cold start + Spring Boot 啟動時間**
  - **症狀**：Spring Boot 3.x JVM 冷啟 ~10 秒 + Lettuce 連 Redis ~2 秒；若 Zeabur scale-to-zero 第一個 request 會 timeout（Zeabur 預設 30s response timeout）.
  - **緩解**：spring-boot-maven-plugin 啟用 AOT processing（`<image><builder>paketobuildpacks/builder:tiny</builder></image>` 或單純 `spring.aot.enabled=true`）冷啟 < 5 秒；Zeabur 設 `min instances = 1` 避免 scale-to-zero（屬部署設定，非 implementation 範疇）.

- **R6: Java client gen vs 手寫 DTO 取捨**
  - **症狀**：openapi-generator-maven-plugin 從 005 OpenAPI 產 Java DTO 自動化好但版本管理痛（每次 005 改要重 build）；手寫快但容易漂移.
  - **緩解**：Phase 6 評估後決定；MVP 先手寫（DTO 只有 PredictionPayload + ErrorResponse 兩個、< 30 欄位），之後若 005 schema 頻繁變動再切自動產 client.

## Notes

- 005 已 Phase 7 完成（commit `fed20e1`），Gateway 可直接針對 005 stable OpenAPI 開發；不需要先動 005.
- 007 React 戰情室目前 MSW mock；006 落地後 007 需把 `apiBaseUrl` 從 mock 切到真 Gateway URL（屬 task #46，非 006 範疇）.
- 憲法 v1.1.0 ratified 2026-04-29，本 plan 對齊 v1.1.0 全 5 原則 gate.
- Phase 5 docker-compose 與 005 共用 redis service：`infra/docker-compose.gateway.yml` 用 `external_links` 或統一寫一個 `infra/docker-compose.full.yml` 起三 service（spring-gw + python-infer + redis）；具體形式 Phase 5 決定.
