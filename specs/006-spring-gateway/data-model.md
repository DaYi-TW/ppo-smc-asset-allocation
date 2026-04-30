# Data Model: Spring Boot API Gateway（006-spring-gateway）

## 1. JPA Entities（PostgreSQL）

所有 entity 採 `@Entity` + Lombok `@Data`/`@Builder`；id 為 UUID（`@GeneratedValue(strategy = GenerationType.UUID)`）。

### 1.1 InferenceLog (`inference_log` 資料表)

| Column | Type | Nullable | Index | 說明 |
|---|---|---|---|---|
| `id` | UUID PK | NO | PK | |
| `request_id` | UUID | NO | UNIQUE | Gateway 注入的 trace id |
| `policy_id` | VARCHAR(64) | NO | INDEX | |
| `observation_hash` | CHAR(64) | NO | INDEX | SHA-256 hex of obs JSON |
| `action` | JSONB | NO | — | `[float * 7]` |
| `value_estimate` | DOUBLE PRECISION | NO | — | |
| `log_prob` | DOUBLE PRECISION | NO | — | |
| `deterministic` | BOOLEAN | NO | — | |
| `inference_latency_ms` | DOUBLE PRECISION | NO | — | 005 自身延遲 |
| `gateway_latency_ms` | DOUBLE PRECISION | NO | — | Gateway overhead |
| `user_id` | VARCHAR(128) | YES | INDEX | JWT subject |
| `created_at` | TIMESTAMPTZ | NO | INDEX (DESC) | server_utc |

### 1.2 EpisodeLog (`episode_log` 資料表)

| Column | Type | Nullable | Index | 說明 |
|---|---|---|---|---|
| `id` | UUID PK | NO | PK | |
| `task_id` | UUID | NO | UNIQUE | client 視角的 task id |
| `policy_id` | VARCHAR(64) | NO | INDEX | |
| `start_date` | DATE | NO | — | |
| `end_date` | DATE | NO | — | |
| `include_smc` | BOOLEAN | NO | — | |
| `seed` | INT | YES | — | |
| `status` | VARCHAR(16) | NO | INDEX | pending / running / completed / failed |
| `summary_json` | JSONB | YES | GIN INDEX | EpisodeSummary（< 10 KB） |
| `trajectory_uri` | TEXT | YES | — | S3 URI（> 1 MB 時） |
| `trajectory_inline` | JSONB | YES | — | 全部 trajectory（< 1 MB 時） |
| `num_steps` | INT | YES | — | |
| `error_class` | VARCHAR(128) | YES | — | failed 時填 |
| `error_message` | TEXT | YES | — | |
| `user_id` | VARCHAR(128) | YES | INDEX | |
| `created_at` | TIMESTAMPTZ | NO | INDEX (DESC) | |
| `started_at` | TIMESTAMPTZ | YES | — | Worker pickup |
| `completed_at` | TIMESTAMPTZ | YES | — | success/fail |

### 1.3 PolicyMetadataEntry (`policy_metadata` 資料表)

| Column | Type | Nullable | Index | 說明 |
|---|---|---|---|---|
| `policy_id` | VARCHAR(64) PK | NO | PK | |
| `policy_path` | TEXT | NO | — | |
| `obs_dim` | INT | NO | — | |
| `loaded_at_utc` | TIMESTAMPTZ | NO | — | |
| `git_commit` | CHAR(40) | YES | — | 從 005 metadata.json |
| `git_dirty` | BOOLEAN | YES | — | |
| `seed` | INT | YES | — | 訓練 seed |
| `final_mean_episode_return` | DOUBLE PRECISION | YES | — | |
| `data_hashes_json` | JSONB | YES | — | 002 Parquet hash dict |
| `package_versions_json` | JSONB | YES | — | |
| `cached_at` | TIMESTAMPTZ | NO | — | Gateway 同步自 005 之時間 |

### 1.4 AuditLog (`audit_log` 資料表)

| Column | Type | Nullable | Index | 說明 |
|---|---|---|---|---|
| `id` | UUID PK | NO | PK | |
| `user_id` | VARCHAR(128) | NO | INDEX | |
| `action` | VARCHAR(64) | NO | INDEX | e.g., POLICY_LOAD, POLICY_DELETE |
| `target` | VARCHAR(256) | YES | — | 操作對象（policy_id, task_id, ...） |
| `details_json` | JSONB | YES | — | 額外結構化內容 |
| `request_id` | UUID | NO | — | |
| `result` | VARCHAR(16) | NO | — | success / failure |
| `created_at` | TIMESTAMPTZ | NO | INDEX (DESC) | |

### 1.5 IdempotencyKey (`idempotency_keys` 資料表)

| Column | Type | Nullable | Index | 說明 |
|---|---|---|---|---|
| `idempotency_key` | VARCHAR(128) PK | NO | PK | client 提供 |
| `endpoint` | VARCHAR(64) | NO | — | e.g., `episode_run` |
| `task_id` | UUID | NO | INDEX | 對應 episode_log.task_id |
| `request_hash` | CHAR(64) | NO | — | request body SHA-256（防止同 key 不同 body） |
| `user_id` | VARCHAR(128) | YES | — | |
| `created_at` | TIMESTAMPTZ | NO | INDEX (TTL cleanup) | |
| `expires_at` | TIMESTAMPTZ | NO | INDEX | created_at + 24h |

## 2. Flyway Migration

`src/main/resources/db/migration/`：

- `V1__init_schema.sql`：建立 5 張表 + index + 必要 constraint。
- `V2__add_idempotency.sql`（範例）：未來 schema 變動 forward migration。
- 規約：每筆 migration 同時提供 forward；rollback 由運維手動處理（非 production 系統不強制 rollback SQL）。

## 3. DTO（Java POJO，camelCase JSON）

對應 spec FR-001、FR-006。所有 DTO 使用 jackson `@JsonNaming(PropertyNamingStrategies.LowerCamelCaseStrategy.class)`。

### 3.1 InferenceRequestDto

```java
public record InferenceRequestDto(
    List<Double> observation,         // 33 or 63 維
    String policyId,                  // null 用 default
    Boolean deterministic              // null 預設 false
) {}
```

### 3.2 InferenceResponseDto

```java
public record InferenceResponseDto(
    UUID inferenceId,
    UUID requestId,                    // Gateway 注入
    String policyId,
    List<Double> action,               // 7 維
    Double value,
    Double logProb,
    RewardComponentsDto rewardComponentsEstimate, // nullable
    Double inferenceLatencyMs,         // 005 自身
    Double gatewayLatencyMs,           // Gateway overhead
    String serverUtc                    // ISO 8601
) {}
```

### 3.3 EpisodeRequestDto

```java
public record EpisodeRequestDto(
    String policyId,
    LocalDate startDate,
    LocalDate endDate,
    Boolean includeSmc,
    Integer seed,
    Boolean deterministic
) {}
```

### 3.4 EpisodeTaskResponseDto（async accept response）

```java
public record EpisodeTaskResponseDto(
    UUID taskId,
    String status,                      // "pending"
    String estimatedCompletionUtc,      // 預估完成（依歷史均值）
    String pollUrl,                     // /api/v1/tasks/{taskId}
    String streamUrl                    // /api/v1/tasks/{taskId}/stream
) {}
```

### 3.5 TaskStatusDto

```java
public record TaskStatusDto(
    UUID taskId,
    String status,                      // pending / running / completed / failed
    String policyId,
    LocalDate startDate,
    LocalDate endDate,
    Integer numSteps,
    EpisodeSummaryDto summary,          // status=completed 時非 null
    String trajectoryUrl,               // pre-signed URL（> 1 MB 時）或 inline endpoint
    String errorClass,                  // failed 時非 null
    String errorMessage,
    String createdAt,
    String startedAt,
    String completedAt
) {}
```

### 3.6 EpisodeSummaryDto

```java
public record EpisodeSummaryDto(
    Double finalNav,
    Double peakNav,
    Double maxDrawdown,
    Double sharpeRatio,
    Double sortinoRatio,
    Double totalReturn,
    Double annualizedReturn,
    Double annualizedVolatility,
    Integer numTrades,
    Double avgTurnover
) {}
```

### 3.7 PolicyDto / PolicyListResponseDto

```java
public record PolicyDto(
    String policyId,
    Integer obsDim,
    Integer actionDim,
    String loadedAtUtc,
    String policyPath,
    PolicyMetadataDto metadata,
    Long inferenceCount
) {}
```

### 3.8 ErrorResponseDto

```java
public record ErrorResponseDto(
    String error,                       // 大寫底線錯誤碼
    String message,
    UUID requestId,
    Map<String, Object> details         // nullable
) {}
```

## 4. Kafka Topics

詳見 `contracts/kafka-topics.md`，摘要如下：

### 4.1 `episode-tasks`

- Partition: 4（demo 規模）
- Key: `taskId` (UUID string)
- Value (JSON):
  ```json
  {
    "taskId": "uuid",
    "policyId": "baseline_seed1",
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
    "includeSmc": true,
    "seed": 1,
    "deterministic": true,
    "userId": "researcher@example.com",
    "requestId": "uuid",
    "submittedAt": "2026-04-29T12:00:00Z"
  }
  ```
- Retention: 7 天

### 4.2 `episode-results`

- Partition: 4
- Key: `taskId`
- Value (JSON):
  ```json
  {
    "taskId": "uuid",
    "status": "completed | failed",
    "policyId": "...",
    "summary": { ... },
    "trajectoryUri": "s3://...",
    "errorClass": null,
    "errorMessage": null,
    "completedAt": "2026-04-29T12:01:00Z"
  }
  ```
- Retention: 30 天

## 5. JWT Principal

```java
public record JwtPrincipal(
    String userId,                     // sub claim
    String role,                       // researcher | reviewer
    Instant issuedAt,
    Instant expiresAt
) implements Principal {
    @Override public String getName() { return userId; }
}
```

claims 解析後注入 Spring Security `Authentication`：`new UsernamePasswordAuthenticationToken(principal, null, List.of(new SimpleGrantedAuthority("ROLE_" + role.toUpperCase())))`。

## 6. 不變量（Invariants）

1. `inference_log.observation_hash` 為 obs JSON 經 `MessageDigest.getInstance("SHA-256")` 後 hex；同 obs 不同次推理 hash 相同。
2. `episode_log.status` 狀態機：`pending → running → completed | failed`；不允許其他轉移；DB level 用 CHECK constraint。
3. `episode_log.trajectory_inline` XOR `trajectory_uri`：兩者恰一非 null（status=completed 時）；status=pending/running 時兩者皆 null。
4. `idempotency_keys.idempotency_key` 唯一；同 key + 不同 `request_hash` → 409 (`IDEMPOTENCY_KEY_MISMATCH`)，不覆寫 task_id。
5. `audit_log.action` 限 enum：`POLICY_LOAD`、`POLICY_DELETE`、`POLICY_SET_DEFAULT`、`USER_CREATED`（未來），DB level CHECK。
6. `policy_metadata.policy_id` 與 005 之 `policy_id` 一致；Gateway 透過 cron job（暫不實作）或事件驅動同步；本 feature 範圍內由 admin 手動觸發 `/admin/sync-policies` 或載入時 upsert。
7. JWT `expiresAt` 過期 → 401 `TOKEN_EXPIRED`；不嘗試刷新。
8. `gatewayLatencyMs` ≥ 0；計算為 `inboundReceiveTime - outboundReplyTime - inferenceLatencyMs`。

## 7. State Transition Diagram (EpisodeTask)

```text
   POST /episode/run                Worker pickup            DB write OK
[client]──────────────▶ pending ─────────────▶ running ────────────────▶ completed
                          │                       │
                          │ Worker pickup         │ exception during 005 call
                          │ exception             │ or DB write
                          ▼                       ▼
                        failed                 failed
```

`status=pending` → 進 Kafka 但未被消費；`status=running` → consumer 拿到後寫此狀態；`status=completed | failed` → terminal。
