# Implementation Plan: Spring Boot API Gateway

> **🚫 SUPERSEDED（2026-05-06）**：本檔對齊 spec v1（含 Kafka / PostgreSQL / MinIO / JWT），於 2026-05-06 與 spec.md 一同走 C-lite 重寫路線。請見最新 [spec.md](./spec.md)（C-lite v2）；對應的 C-lite plan / tasks / contracts 將由下一輪 `/speckit.plan` 重新產生。本檔僅保留供 git history 對照、**禁止用於 implementation**。

---

**Branch**: `006-spring-gateway` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-spring-gateway/spec.md`

## Summary

Spring Boot 3.x + Java 17 API Gateway，作為 React 戰情室（007）與 Python 推理服務（005）間的中介。三大職責：(a) 統一 REST 入口（camelCase JSON、JWT 認證、CORS、熔斷器、requestId tracing）；(b) Kafka 解耦長任務（episode 推理 ≥ 1 年區間走 producer/consumer，Worker 內聚於同 Spring Boot app）；(c) PostgreSQL 持久化推理日誌與 audit log，trajectory blob > 1 MB 落地 S3-compatible 物件儲存。OpenAPI 3.1 由 springdoc-openapi 自動產生供 007 TypeScript client gen 消費；對 005 之 Java client 由 openapi-generator-maven-plugin 從 `specs/005-inference-service/contracts/openapi.yaml` 產出。

## Technical Context

**Language/Version**: Java 17（LTS）、Spring Boot 3.2.x（與憲法 Tech Stack 對齊）、Maven 3.9 build（不採 Gradle，理由見 R1）。
**Primary Dependencies**: spring-boot-starter-web、spring-boot-starter-actuator、spring-boot-starter-data-jpa、spring-boot-starter-security、spring-kafka 3.1、springdoc-openapi-starter-webmvc-ui 2.3、micrometer-registry-prometheus、resilience4j-spring-boot3 (circuit breaker)、aws-sdk-s3 v2、flyway-core、jjwt 0.12、lombok、testcontainers (postgres + kafka)、hikariCP（內建）。
**Storage**: PostgreSQL 14+（主 DB）；S3-compatible（trajectory blob > 1 MB）；無 Redis（暫不引入，未來可加）。
**Testing**: JUnit 5、Mockito、testcontainers (PostgreSQL + Kafka)、spring-boot-starter-test、WireMock（mock 005 端點）；覆蓋率 ≥ 80%（SC-005）。
**Target Platform**: K8s 部署（容器化）；本地 docker-compose 含 Gateway + Postgres + Kafka + MinIO。
**Project Type**: Single backend project；Maven 專案 root `services/gateway/`（與未來 services/inference/ 平行；本 repo 採 monorepo 結構）。
**Performance Goals**: `POST /api/v1/inference/infer` 端對端 p99 < 100 ms（含 005 50 ms + Gateway overhead 50 ms）；async episode 任務 100 並發 60 秒內完成（SC-001, SC-002）。
**Constraints**: 無共享 DB 連線給其他服務、無共享記憶體（憲法 Principle IV）；JWT signing key 從 env var 注入、不 commit；trajectory blob > 1 MB 不入 DB（SC-008）；Kafka exactly-once（producer idempotence + consumer manual commit after DB write）。
**Scale/Scope**: 預期 < 100 RPS（research demo 規模）；同時 ≤ 50 in-flight async episode 任務；DB 紀錄上限 ~10 萬列 inference_log + ~1 千列 episode_log（research lifetime）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依憲法 v1.1.0 五大原則逐項評估：

### Principle I — 可重現性（NON-NEGOTIABLE）

✅ **PASS（with caveat）**

- Gateway 不執行 RL 計算或 reward；僅代理推理請求 → 不改變底層可重現性。
- DB 紀錄含 `policy_id`、`observation_hash`、`action`、`request_id`、`server_utc`，研究者可由 DB 反查推理當下使用之 005 policy commit hash（透過 `policy_metadata.git_commit`）。
- Caveat：Gateway 之 `requestId`（UUID）與 `gatewayLatencyMs` 為非決定值，**不參與**回傳 005 結果的計算路徑；只附加在 envelope，不影響 byte-identical 保證。
- DB schema migration 由 Flyway 鎖定（FR-013），同 commit 下 schema 一致。

### Principle II — 特徵可解釋性

✅ **PASS**

- Gateway 不解釋 SMC 特徵；但 episode_log 端對端透傳 005 的 SMC raw 訊號（`bos`、`choch` 等），不做任何聚合或擷取 → 前端可拿到原始解釋資料。
- Audit log 額外提供「人為操作」追溯（policy 載入/卸載 by 誰、何時）。

### Principle III — 風險優先獎勵（NON-NEGOTIABLE）

✅ **N/A**

- Gateway 不定義 reward；reward 三項分量（log_return、drawdown_penalty、turnover_penalty）由 005 計算後透傳。
- 但介面層保留：episode_log 之 `rewardComponents` 為三欄 JSON object（不可被合併或聚合），由 003 info schema 對齊。

### Principle IV — 微服務解耦（核心）

✅ **PASS（核心對應）**

- 本 feature 即憲法 Principle IV「Java/Spring Boot」一層的具體實作。
- Gateway 與 005 之間僅透過 HTTP API（openapi.yaml 為契約）；Worker 與 Gateway 同 JVM 但走 Kafka topic 邏輯解耦（未來可拆 deploy）。
- 不共享 DB 連線：本 Gateway 之 PostgreSQL 為自己專屬，**不**讓 005 或 007 直連。
- 005 / 006 / 007 三層皆可獨立部署、獨立測試（test profile 用 WireMock + testcontainers 完全隔離）。

### Principle V — 規格先行（NON-NEGOTIABLE）

✅ **PASS**

- spec.md 已通過 quality checklist（specs/006-spring-gateway/checklists/requirements.md）。
- 本 plan 之 contracts/ 為「先寫契約再實作」，OpenAPI 3.1 spec + DB schema + Kafka topic schema 三類契約明文。
- tasks.md 排程 Phase 2 先寫 contract test、Phase 3+ 才實作 endpoint。

**Initial Constitution Check 結論**：所有 5 條原則無違反；無需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/006-spring-gateway/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── openapi.yaml         # OpenAPI 3.1 spec (前端契約)
│   ├── error-codes.md       # 錯誤碼字典
│   ├── kafka-topics.md      # Kafka topic schema (episode-tasks, episode-results)
│   └── db-schema.md         # PostgreSQL DDL 摘要 + Flyway migration 規約
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

採 monorepo + maven module 佈局：

```text
services/gateway/                          # Maven project root
├── pom.xml
├── Dockerfile
├── docker-compose.yml                     # Gateway + Postgres + Kafka + MinIO
├── src/main/java/com/ppo_smc/gateway/
│   ├── GatewayApplication.java            # Spring Boot main
│   ├── config/                            # SecurityConfig, KafkaConfig, RestTemplateConfig, ObjectStorageConfig, OpenApiConfig
│   ├── controllers/                       # Inference/Episode/Task/Policy/Logs/Admin Controllers
│   ├── services/                          # InferenceProxyService, EpisodeTaskService, ObjectStorageService, AuditLogService, IdempotencyService
│   ├── kafka/                             # EpisodeTaskProducer, EpisodeResultConsumer, EpisodeWorker
│   ├── repositories/                      # JPA Repositories (5 個)
│   ├── entities/                          # JPA @Entity (5 個)
│   ├── dtos/                              # camelCase request/response DTO
│   ├── inference_client/                  # openapi-generator 生成的 005 Java client (git-ignored)
│   ├── security/                          # JwtAuthenticationFilter, JwtPrincipal
│   ├── observability/                     # RequestIdFilter, MetricsConfig, JsonLogConfig
│   └── exceptions/                        # GlobalExceptionHandler + 自訂例外
├── src/main/resources/
│   ├── application.yaml                   # 預設 + dev profile
│   ├── application-test.yaml              # H2 + embedded kafka
│   ├── application-prod.yaml
│   ├── log4j2.xml                         # JSON appender
│   └── db/migration/                      # Flyway V1__, V2__, ...
└── src/test/java/com/ppo_smc/gateway/
    ├── controllers/                       # @WebMvcTest + Mock service
    ├── services/                          # WireMock mock 005
    ├── kafka/                             # @EmbeddedKafka
    ├── integration/                       # testcontainers (Postgres + Kafka) end-to-end
    └── contract/                          # OpenAPI validity, DB schema contract
```

**Structure Decision**: 將 Gateway 放在 `services/gateway/` 為獨立 maven module；未來若新增 Java 服務（如另一 ETL gateway）可平行建立 `services/<name>/`。`services/inference/` 不在本 repo（為純 Python，留在 src/inference_service/），但 `services/gateway/` 之 inference Java client 由 005 OpenAPI yaml 產生，build 流程在 `pom.xml` 中以 openapi-generator-maven-plugin 設定，目標目錄 `target/generated-sources/openapi`（不入 git）。

## Complexity Tracking

> 無違反 Constitution，本節不適用。
