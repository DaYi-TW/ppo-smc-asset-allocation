# Error Codes: 推理服務（005-inference-service）— C-lite 版

**Last Major Revision**: 2026-05-06

統一錯誤回應 schema 與錯誤碼字典。對應 spec FR-012（結構化 log）+ data-model.md §4 ErrorResponse。

## Error Response 格式

所有非 2xx 回應 body 為：

```json
{
  "code": "INFERENCE_BUSY",
  "message": "Another inference is currently running. Retry later.",
  "error_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp_utc": "2026-05-06T08:42:13.456Z"
}
```

`error_id` 是 uuid4，對應 stderr 寫的 stack trace。response body 不洩漏 stack trace（FR-012）。

## 錯誤碼字典

### 4xx — Client errors

| Code | HTTP | 觸發條件 | 對應 spec | 操作建議 |
|------|------|----------|-----------|----------|
| `INFERENCE_BUSY` | 409 | mutex 已被另一次 inference 佔用 | FR-003 | 等待 30~60 秒後 retry |
| `NO_PREDICTION_YET` | 404 | `/infer/latest` 但 cache 為空（從未跑過） | FR-008 | 先呼叫 `/infer/run` 或等下次 scheduled |
| `PREDICTION_EXPIRED` | 404 | `/infer/latest` 但 cache 已過 TTL（7 天無新預測） | FR-008 | 觸發新一次 inference |

### 5xx — Server errors

| Code | HTTP | 觸發條件 | 對應 spec | 操作建議 |
|------|------|----------|-----------|----------|
| `POLICY_NOT_LOADED` | 503 | 服務啟動但 policy.zip 載入失敗 | edge case | 檢查 `POLICY_PATH` env var、policy.zip 完整性、重啟容器 |
| `REDIS_UNREACHABLE` | 503 | Redis client 連線失敗 | edge case | 檢查 redis container / Zeabur Redis 狀態 |
| `DATA_STALE` | 503 | data/raw 最後一日 > 3 天前（warning，非硬阻塞） | edge case | 跑 `ppo-smc-data update` 後重 build image |
| `INFERENCE_FAILED` | 500 | handler 內部例外（policy.predict / env.step 噴錯） | edge case | 看 stderr stack trace（用 error_id 對應）|
| `SCHEDULER_DEAD` | 503 | APScheduler 已死、無下次 trigger | edge case | 重啟容器；若反覆發生回報 issue |

## Log Event 對照

每個 error code 對應一筆 stdout JSON log，event 欄位如下：

| Event (log) | 對應 Error Code | Level |
|---|---|---|
| `inference_busy_rejected` | INFERENCE_BUSY | INFO |
| `latest_cache_empty` | NO_PREDICTION_YET | INFO |
| `latest_cache_expired` | PREDICTION_EXPIRED | WARNING |
| `policy_load_failed` | POLICY_NOT_LOADED | ERROR |
| `redis_publish_failed` | （非 HTTP error，僅 log） | WARNING |
| `redis_connection_failed` | REDIS_UNREACHABLE | ERROR |
| `data_stale_warning` | DATA_STALE | WARNING |
| `inference_completed` | (success) | INFO |
| `inference_failed` | INFERENCE_FAILED | ERROR |
| `scheduled_trigger_fired` | (success) | INFO |
| `scheduled_inference_failed` | (success — scheduler 仍活著) | ERROR |
| `scheduler_dead` | SCHEDULER_DEAD | CRITICAL |

## 不在錯誤碼內

- **HTTP 401 / 403**：無 auth（依賴 006 Gateway）
- **HTTP 429 rate limit**：無；mutex 機制取代
- **HTTP 400 invalid request**：本 service 的 endpoint 都無 request body 或極簡（無從 invalid）
- **OpenAPI validation error**：FastAPI 自動回 422，不另外定義
