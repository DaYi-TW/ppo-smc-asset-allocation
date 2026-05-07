# Kafka Topics Contract

> **🚫 SUPERSEDED（2026-05-06）**：C-lite v2 已**移除 Kafka**（spec FR-018，論文規模採 Redis pub/sub），本檔不再適用，**禁止用於 implementation**。對應的 Redis pub/sub channel 規約（`predictions:latest`）寫於 005 spec 而非 006，因 Gateway 為消費端。

---

定義 episode 解耦所用之 Kafka topic schema 與生產/消費規約。對應 spec FR-007 ~ FR-011、data-model §4。

## Topic 列表

### 1. `episode-tasks`

派發長時間 episode 推理任務。

- **Partition**: 4（demo 規模；future scale 由 ops 調整）
- **Replication factor**: 3（production）/ 1（local dev）
- **Retention**: 7 天（604800000 ms）
- **Cleanup policy**: `delete`
- **Key**: `taskId`（UUID 字串）
- **Value codec**: JSON UTF-8

#### Value Schema

```json
{
  "taskId": "550e8400-e29b-41d4-a716-446655440000",
  "policyId": "baseline_seed1",
  "startDate": "2025-01-01",
  "endDate": "2025-12-31",
  "includeSmc": true,
  "seed": 1,
  "deterministic": true,
  "userId": "researcher@example.com",
  "requestId": "uuid-v4",
  "submittedAt": "2026-04-29T12:00:00Z",
  "schemaVersion": 1
}
```

| Field | Type | 必填 | 說明 |
|---|---|---|---|
| `taskId` | string (UUID) | ✓ | 同 partition key |
| `policyId` | string \| null | ✓ | null 用 005 default |
| `startDate` | string (ISO date) | ✓ | |
| `endDate` | string (ISO date) | ✓ | |
| `includeSmc` | boolean | ✓ | |
| `seed` | integer \| null | ✓ | |
| `deterministic` | boolean | ✓ | |
| `userId` | string \| null | ✓ | JWT subject |
| `requestId` | string (UUID) | ✓ | trace 用 |
| `submittedAt` | string (date-time) | ✓ | producer 寫入時刻 |
| `schemaVersion` | integer | ✓ | 目前 1；變更時 bump |

#### Producer 設定

```yaml
spring.kafka.producer:
  bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
  key-serializer: org.apache.kafka.common.serialization.StringSerializer
  value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
  properties:
    acks: all
    enable.idempotence: true
    retries: 3
    max.in.flight.requests.per.connection: 5
    compression.type: snappy
    linger.ms: 5
    batch.size: 16384
```

#### Consumer 設定

```yaml
spring.kafka.consumer:
  bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
  group-id: episode-worker
  key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
  value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
  enable-auto-commit: false
  isolation-level: read_committed
  max-poll-records: 10
  properties:
    spring.json.trusted.packages: com.ppo_smc.gateway.kafka.dto
spring.kafka.listener:
  ack-mode: MANUAL_IMMEDIATE
```

### 2. `episode-results`

Worker 處理完成後寫入，用於 Gateway 內 SSE event publishing 與 audit。

- **Partition**: 4
- **Retention**: 30 天
- **Key**: `taskId`
- **Value codec**: JSON UTF-8

#### Value Schema

```json
{
  "taskId": "uuid",
  "status": "completed",
  "policyId": "baseline_seed1",
  "summary": {
    "finalNav": 1.082,
    "peakNav": 1.124,
    "maxDrawdown": 0.085,
    "sharpeRatio": 1.34,
    "...": "..."
  },
  "trajectoryUri": "s3://gateway-bucket/episodes/uuid.json.gz",
  "trajectoryInline": null,
  "numSteps": 252,
  "startedAt": "2026-04-29T12:00:01Z",
  "completedAt": "2026-04-29T12:00:08Z",
  "errorClass": null,
  "errorMessage": null,
  "schemaVersion": 1
}
```

`status="failed"` 時 `summary`、`trajectoryUri`、`trajectoryInline`、`numSteps` 為 null；`errorClass`、`errorMessage` 必填。

## 處理流程

```text
Client
  │  POST /api/v1/episode/run
  ▼
Gateway Controller (EpisodeController)
  │  validate, idempotency check
  │  insert episode_log row (status=pending)
  │  produce → episode-tasks
  │  return 202 + taskId
  ▼
Kafka topic: episode-tasks
  │
  ▼
EpisodeWorker @KafkaListener
  │  poll record
  │  update episode_log.status = running, started_at = now()
  │  call 005 /v1/episode/run (REST, with circuit breaker)
  │  if trajectory > 1 MB: upload to S3, get URI
  │  update episode_log.status = completed, summary, trajectory_*
  │  produce → episode-results
  │  ack offset (MANUAL_IMMEDIATE)
  ▼
Kafka topic: episode-results
  │
  ▼
EpisodeResultConsumer @KafkaListener
  │  publish SSE event to subscribers (taskId)
  │  no DB write (already done by worker)
```

## 失敗處理

### Producer 失敗（episode-tasks）

- 自動重試 3 次（producer config `retries=3`）。
- 仍失敗 → controller 回 503 `KAFKA_UNAVAILABLE`、`episode_log` 維持 status=pending（Worker 不會撿到，但 client 可重新提交）。
- 補救：admin 可手動觸發 `/admin/republish-pending-tasks`（暫不實作，留 future TODO）。

### Worker 處理失敗

- 005 回 5xx：exponential backoff 重試 3 次（1s、4s、16s）。
- 仍失敗 → 寫 `episode_log.status=failed` + `error_class`、`error_message`；ack offset（avoid stuck）。
- 005 回 4xx（如 OBSERVATION_DIM_MISMATCH）：不重試，直接 status=failed。
- DB 寫入失敗：不 ack offset，下次 poll 會重試（最終由 Kafka retention 兜底）。

### Consumer offset 提交時機

**僅在以下三事件全部成功後** ack：

1. 005 推理回應收到（或最終失敗確定）。
2. `episode_log` UPDATE 成功（含 status, summary, trajectory_uri）。
3. `episode-results` topic produce 成功。

任一失敗 → 不 ack，重新處理（依 Idempotency 由 task_id unique constraint 防雙寫）。

## 不變量

1. 同 `taskId` 在 `episode-tasks` 與 `episode-results` 中各最多一筆「最終 ack」記錄；中間重試不算。
2. `episode_log.task_id` 為 UNIQUE → 雙重寫入會失敗、不會產生重複 row。
3. `episode-results` 之 `status` 必為 `completed | failed`，不會是 `pending | running`。
4. `submittedAt` ≤ `startedAt` ≤ `completedAt`（若皆非 null）。

## Schema 演進規約

- 新增 optional field：bump `schemaVersion`、producer/consumer 仍向後相容。
- 移除/重命名 field：MAJOR change，需新 topic（如 `episode-tasks-v2`）並雙寫過渡 30 天。
- consumer MUST ignore 未知 field（Jackson 預設行為）。

## 不在範圍

- 跨叢集 mirror（MirrorMaker 2）。
- Schema Registry（demo 階段不引入；JSON schemaVersion 自管）。
- Compaction topic（episode-tasks 採 delete policy）。
