# DB Schema Contract

PostgreSQL DDL 摘要與 Flyway migration 規約。對應 spec FR-012 ~ FR-014、data-model §1。

## V1__init_schema.sql

```sql
-- 1. inference_log
CREATE TABLE inference_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id               UUID NOT NULL UNIQUE,
    policy_id                VARCHAR(64) NOT NULL,
    observation_hash         CHAR(64) NOT NULL,
    action                   JSONB NOT NULL,
    value_estimate           DOUBLE PRECISION NOT NULL,
    log_prob                 DOUBLE PRECISION NOT NULL,
    deterministic            BOOLEAN NOT NULL,
    inference_latency_ms     DOUBLE PRECISION NOT NULL,
    gateway_latency_ms       DOUBLE PRECISION NOT NULL,
    user_id                  VARCHAR(128),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inference_log_policy_id ON inference_log(policy_id);
CREATE INDEX idx_inference_log_observation_hash ON inference_log(observation_hash);
CREATE INDEX idx_inference_log_user_id ON inference_log(user_id);
CREATE INDEX idx_inference_log_created_at_desc ON inference_log(created_at DESC);

-- 2. episode_log
CREATE TABLE episode_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                  UUID NOT NULL UNIQUE,
    policy_id                VARCHAR(64) NOT NULL,
    start_date               DATE NOT NULL,
    end_date                 DATE NOT NULL,
    include_smc              BOOLEAN NOT NULL,
    seed                     INTEGER,
    status                   VARCHAR(16) NOT NULL,
    summary_json             JSONB,
    trajectory_uri           TEXT,
    trajectory_inline        JSONB,
    num_steps                INTEGER,
    error_class              VARCHAR(128),
    error_message            TEXT,
    user_id                  VARCHAR(128),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at               TIMESTAMPTZ,
    completed_at             TIMESTAMPTZ,

    CONSTRAINT chk_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT chk_date_order CHECK (start_date < end_date),
    CONSTRAINT chk_trajectory_xor CHECK (
        (status NOT IN ('completed')) OR
        ((trajectory_uri IS NOT NULL AND trajectory_inline IS NULL) OR
         (trajectory_uri IS NULL AND trajectory_inline IS NOT NULL))
    ),
    CONSTRAINT chk_failed_has_error CHECK (
        status <> 'failed' OR (error_class IS NOT NULL AND error_message IS NOT NULL)
    )
);

CREATE INDEX idx_episode_log_policy_id ON episode_log(policy_id);
CREATE INDEX idx_episode_log_status ON episode_log(status);
CREATE INDEX idx_episode_log_user_id ON episode_log(user_id);
CREATE INDEX idx_episode_log_created_at_desc ON episode_log(created_at DESC);
CREATE INDEX idx_episode_log_summary_json_gin ON episode_log USING GIN (summary_json);

-- 3. policy_metadata
CREATE TABLE policy_metadata (
    policy_id                       VARCHAR(64) PRIMARY KEY,
    policy_path                     TEXT NOT NULL,
    obs_dim                         INTEGER NOT NULL,
    loaded_at_utc                   TIMESTAMPTZ NOT NULL,
    git_commit                      CHAR(40),
    git_dirty                       BOOLEAN,
    seed                            INTEGER,
    final_mean_episode_return       DOUBLE PRECISION,
    final_mean_drawdown             DOUBLE PRECISION,
    final_mean_turnover             DOUBLE PRECISION,
    data_hashes_json                JSONB,
    package_versions_json           JSONB,
    config_sha256                   CHAR(64),
    cached_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. audit_log
CREATE TABLE audit_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  VARCHAR(128) NOT NULL,
    action                   VARCHAR(64) NOT NULL,
    target                   VARCHAR(256),
    details_json             JSONB,
    request_id               UUID NOT NULL,
    result                   VARCHAR(16) NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_result CHECK (result IN ('success', 'failure')),
    CONSTRAINT chk_action CHECK (action IN (
        'POLICY_LOAD', 'POLICY_DELETE', 'POLICY_SET_DEFAULT',
        'TASK_RETRY', 'EXPORT_LOGS', 'CONFIG_CHANGE'
    ))
);

CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);
CREATE INDEX idx_audit_log_created_at_desc ON audit_log(created_at DESC);

-- 5. idempotency_keys
CREATE TABLE idempotency_keys (
    idempotency_key          VARCHAR(128) PRIMARY KEY,
    endpoint                 VARCHAR(64) NOT NULL,
    task_id                  UUID NOT NULL,
    request_hash             CHAR(64) NOT NULL,
    user_id                  VARCHAR(128),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at               TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_idempotency_keys_task_id ON idempotency_keys(task_id);
CREATE INDEX idx_idempotency_keys_expires_at ON idempotency_keys(expires_at);
```

## V2__add_pgcrypto.sql

```sql
-- gen_random_uuid() 需要 pgcrypto extension（PG14+ 內建 pgcrypto）
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

(視部署環境，部分管理 PG 服務 V1 即可使用 `gen_random_uuid()`，視情況併入 V1)

## Migration 規約

1. **Forward only**：每個版本檔（V<N>__<desc>.sql）只能新增、不可修改既有檔案內容。修錯先建 V<N+1>__fix_<desc>.sql。
2. **不寫 rollback SQL**：本 demo 系統不強制 rollback；production 部署 rollback 由運維手動處理（例如 `pg_restore` 前一晚備份）。
3. **大表變更**：避免 `ALTER TABLE ... ADD COLUMN NOT NULL DEFAULT ...` 鎖整表，改 `ADD COLUMN NULL` → backfill → `ALTER COLUMN SET NOT NULL` 三步。
4. **Index 建立**：> 100 萬列的表用 `CREATE INDEX CONCURRENTLY`（Flyway 需設 `mixed = true` 或外部執行）。
5. **檔名 convention**：`V<N>__<lower_snake_case_description>.sql`，N 為遞增整數（不允許跳號）。

## DataSource 設定（HikariCP）

```yaml
spring.datasource:
  url: ${DB_URL}
  username: ${DB_USER}
  password: ${DB_PASSWORD}
  hikari:
    maximum-pool-size: 20
    minimum-idle: 5
    connection-timeout: 5000
    idle-timeout: 300000
    max-lifetime: 1200000
    leak-detection-threshold: 60000
```

連線池飽和（`maximum-pool-size` 達上限且新請求 5 秒內取不到）→ 拋 `SQLException` → GlobalExceptionHandler 轉 503 `DB_UNAVAILABLE`（FR error-codes）。

## JPA 設定

```yaml
spring.jpa:
  hibernate:
    ddl-auto: validate         # 不允許 hibernate 自動 ALTER schema；schema 由 Flyway 管
  properties:
    hibernate.dialect: org.hibernate.dialect.PostgreSQLDialect
    hibernate.jdbc.batch_size: 50
    hibernate.order_inserts: true
    hibernate.order_updates: true
spring.flyway:
  enabled: true
  locations: classpath:db/migration
  baseline-on-migrate: true
```

## 索引策略總結

| 表 | Index | 目的 |
|---|---|---|
| inference_log | (created_at DESC) | 列表分頁（最近優先） |
| inference_log | (policy_id) | 過濾單一 policy |
| inference_log | (observation_hash) | 重複 obs 統計 |
| episode_log | (status) | Worker 撿 pending 任務（雖非 from-scratch source） |
| episode_log | GIN summary_json | `summary_json->>'sharpe_ratio' > X` 查詢 |
| audit_log | (created_at DESC) | 列表分頁 |
| idempotency_keys | (expires_at) | TTL cleanup job |

## TTL Cleanup Job（未來）

- `idempotency_keys.expires_at < NOW()` 之列每天清一次（Spring `@Scheduled`，cron 03:00 UTC）。
- 本 feature 範圍內可不實作（24 小時 TTL 表規模上限約 100 萬列、可 tolerate）；標 future TODO。

## 不在範圍

- Read replica。
- Partitioning（時間分區）。
- 跨資料中心同步。
