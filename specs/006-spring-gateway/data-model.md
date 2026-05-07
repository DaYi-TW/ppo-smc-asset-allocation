# Data Model: Spring Boot API Gateway (C-lite v2)

**Status**: C-lite v2（2026-05-06）— Gateway 為 stateless proxy，無資料庫、無 entity。本檔定義 DTO（Java POJO）schema 與 JSON wire format。對應 spec.md FR-001 ~ FR-014。

## 1. 設計總則

- 全部 DTO 為 **immutable POJO**（用 Java 17+ `record` 或 Lombok `@Value`）；明示 nullable 欄位用 `@JsonInclude(NON_NULL)`.
- 對外 JSON 一律 **camelCase + ISO 8601 日期字串**.
- 對 005 的 RestClient 解析回應時，DTO 加 `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)` 自動 snake_case → camelCase（見 research.md R5）.
- DTO 不含業務邏輯；轉換 / fan-out 邏輯在 service layer（`InferenceClient`、`PredictionBroadcaster`）.

## 2. DTO 列表

### 2.1 `PredictionPayloadDto`（核心 — 與 005 PredictionPayload 對齊）

對應前端 LivePredictionCard 與 SSE event payload。一字不漏 mirror 005 schema（snake_case 自動轉 camelCase）.

```java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record PredictionPayloadDto(
    String asOfDate,                  // 005: as_of_date          ISO date "2026-04-28"
    String nextTradingDayTarget,      // 005: next_trading_day_target
    String policyPath,                // 005: policy_path
    boolean deterministic,
    Map<String, Double> targetWeights,// 005: target_weights      {NVDA: 0.1, ...}
    boolean weightsCapped,            // 005: weights_capped
    boolean renormalized,
    ContextDto context,
    String triggeredBy,               // 005: triggered_by         "manual" | "scheduled"
    String inferenceId,               // 005: inference_id         UUID
    String inferredAtUtc              // 005: inferred_at_utc      ISO 8601
) {}

public record ContextDto(
    String dataRoot,
    boolean includeSmc,
    int nWarmupSteps,
    double currentNavAtAsOf
) {}
```

**Validation**:
- `asOfDate`: 非空、ISO date.
- `targetWeights`: 7 個 key（NVDA、AMD、TSM、MU、GLD、TLT、CASH），sum ≈ 1.0（容差 1e-6）.
- `triggeredBy`: ∈ {"manual", "scheduled"}.
- `inferenceId`: UUID v4 字串.

**Wire JSON example**（前端視角，Gateway 輸出）：
```json
{
  "asOfDate": "2026-04-28",
  "nextTradingDayTarget": "first session after 2026-04-28 (apply at next open)",
  "policyPath": "/app/runs/20260506_004455_659b8eb_seed42/final_policy.zip",
  "deterministic": true,
  "targetWeights": {"NVDA": 0.1, "AMD": 0.1, "TSM": 0.1, "MU": 0.1, "GLD": 0.1, "TLT": 0.1, "CASH": 0.4},
  "weightsCapped": false,
  "renormalized": false,
  "context": {"dataRoot": "data/raw", "includeSmc": true, "nWarmupSteps": 100, "currentNavAtAsOf": 1.0},
  "triggeredBy": "manual",
  "inferenceId": "550e8400-e29b-41d4-a716-446655440000",
  "inferredAtUtc": "2026-05-06T00:00:00Z"
}
```

---

### 2.2 `ErrorResponseDto`

統一錯誤格式（spec FR-005）.

```java
public record ErrorResponseDto(
    String error,        // ErrorCode enum string
    String message,      // 人類可讀描述
    String requestId,    // UUID v4
    Map<String, Object> details  // optional, nullable
) {}
```

**ErrorCode enum**（對應 contracts/error-codes.md）：
- `InferenceServiceUnavailable`: 005 連不上（502/503/504 from 005 視為皆此 code）.
- `InferenceTimeout`: 005 呼叫超過 90 秒.
- `InferenceBusy`: 005 回 409 INFERENCE_BUSY 透傳（status 409）.
- `PredictionNotReady`: 005 回 404 NO_PREDICTION_YET 透傳（status 404）.
- `RedisUnavailable`: SSE 訂閱失敗 / cache 無法讀（status 503）.
- `BadRequest`: 4xx from 005 透傳.
- `InternalServerError`: Gateway 自身 unhandled exception（status 500）.

---

### 2.3 `HealthDto`（`/api/v1/inference/healthz` 回應）

純 pass-through 005 health（spec FR-003）.

```java
public record HealthDto(
    String status,                // "ok" | "degraded"
    int uptimeSeconds,
    boolean policyLoaded,
    boolean redisReachable,
    String lastInferenceAtUtc,    // nullable ISO 8601
    String nextScheduledRunUtc    // nullable ISO 8601
) {}
```

---

### 2.4 `PredictionEventDto`（SSE event 包裝）

SSE 廣播時的 outer envelope（FR-006）.

```java
public record PredictionEventDto(
    String eventType,             // "prediction" | "degraded" | "ping"
    String emittedAtUtc,          // Gateway 廣播時間
    PredictionPayloadDto payload  // null when eventType == "ping"
) {}
```

**Event types**:
- `prediction`: 收到 Redis publish 時 fan-out；payload 為最新 prediction.
- `degraded`: Redis 斷線、切到 polling fallback 時送一次（前端可顯示 toast）.
- `ping`: 每 15 秒 keep-alive（FR-008），無 payload.

**SSE wire format**:
```
event: prediction
data: {"eventType":"prediction","emittedAtUtc":"2026-05-06T05:30:01Z","payload":{...}}

```

---

### 2.5 `GatewayHealthDto`（`/actuator/health` 自訂 component 用）

由 `HealthIndicator` bean 派生；Spring Boot Actuator 自動 wrap 成標準 health response.

組件結構（actuator/health 回應）：
```json
{
  "status": "UP",
  "components": {
    "inference": {"status": "UP", "details": {"url": "http://python-infer:8000", "latencyMs": 32}},
    "redis":     {"status": "UP", "details": {"url": "redis://redis:6379/0"}}
  }
}
```

實作上：
- `InferenceHealthIndicator implements HealthIndicator` — 呼叫 005 `/healthz`，2 秒 timeout，UP/DOWN 判定 + latency 計入 details.
- `RedisHealthIndicator` — Spring Boot 自帶（spring-boot-starter-data-redis 帶入），無需自己寫.

---

## 3. Schema parity invariant（與 005）

**核心契約**（spec FR-004 + plan G-V-2）：

| 005 PredictionPayload key | Gateway PredictionPayloadDto field | 轉換 |
|---|---|---|
| `as_of_date` | `asOfDate` | snake → camel |
| `next_trading_day_target` | `nextTradingDayTarget` | snake → camel |
| `policy_path` | `policyPath` | snake → camel |
| `deterministic` | `deterministic` | identity |
| `target_weights` | `targetWeights` | snake → camel；inner Map keys 不變（NVDA、AMD、…） |
| `weights_capped` | `weightsCapped` | snake → camel |
| `renormalized` | `renormalized` | identity |
| `context.data_root` | `context.dataRoot` | snake → camel |
| `context.include_smc` | `context.includeSmc` | snake → camel |
| `context.n_warmup_steps` | `context.nWarmupSteps` | snake → camel |
| `context.current_nav_at_as_of` | `context.currentNavAtAsOf` | snake → camel |
| `triggered_by` | `triggeredBy` | snake → camel |
| `inference_id` | `inferenceId` | snake → camel |
| `inferred_at_utc` | `inferredAtUtc` | snake → camel |

**Invariant**（contract test 必驗）：
- 所有 numerical 欄位（target_weights values、currentNavAtAsOf）byte-identical from 005，禁止 rounding / format 變動.
- 005 OpenAPI 有的欄位 Gateway DTO 全 cover（用 contract test 解析 005 OpenAPI 比對 DTO field 數量）.
- 未來 005 schema 加新欄位時，DTO 加 `@JsonAnySetter` + `@JsonAnyGetter` 透傳，CI 跑 schema parity test 提醒手工同步.
