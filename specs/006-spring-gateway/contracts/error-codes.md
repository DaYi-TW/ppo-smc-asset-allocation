# Error Codes: Spring Gateway

統一錯誤回應 schema 與錯誤碼表。對應 spec FR-006、data-model §9。

## Error Response 格式

```json
{
  "error": "INFERENCE_SERVICE_UNAVAILABLE",
  "message": "Inference service did not respond within 5s",
  "requestId": "uuid",
  "details": { "circuitBreakerState": "OPEN" }
}
```

- `error`：大寫底線。
- `message`：英文，不洩漏 stack trace。
- `requestId`：UUID，與 log MDC 一致；可串接 audit/observability。
- `details`：可選 object。

## 錯誤碼表

| Code | HTTP | 觸發 | 訊息範例 |
|---|---|---|---|
| `BAD_REQUEST` | 400 | request body / parameter 驗證失敗 | `Invalid request: ...` |
| `OBSERVATION_DIM_MISMATCH` | 400 | obs 維度不符（從 005 直接傳遞） | `Expected obs dim 63, got 33` |
| `OBSERVATION_NAN` | 400 | obs 含 NaN/Inf | |
| `INVALID_DATE_RANGE` | 400 | start ≥ end | |
| `EPISODE_RANGE_TOO_LARGE_FOR_SYNC` | 413 | sync 模式但 > 1 年 | |
| `EPISODE_RANGE_TOO_LARGE` | 400 | async 模式但 > episode_max_days | |
| `IDEMPOTENCY_KEY_MISMATCH` | 409 | 同 key 但 request body 不同 | |
| `TOKEN_MISSING` | 401 | 缺 Authorization header | |
| `TOKEN_INVALID` | 401 | JWT 簽章驗證失敗 | |
| `TOKEN_EXPIRED` | 401 | JWT exp claim 已過 | |
| `INSUFFICIENT_PERMISSIONS` | 403 | role 不足（reviewer 嘗試寫操作） | |
| `POLICY_NOT_FOUND` | 404 | policyId 不存在於 005 或 Gateway cache | |
| `POLICY_ID_EXISTS` | 409 | load 時 policyId 已存在 | |
| `POLICY_LOAD_FAILED` | 400 | 005 回 POLICY_LOAD_FAILED（透傳） | |
| `TASK_NOT_FOUND` | 404 | taskId 在 episode_log 不存在 | |
| `INFERENCE_SERVICE_UNAVAILABLE` | 503 | 005 連通失敗或 circuit breaker OPEN | |
| `KAFKA_UNAVAILABLE` | 503 | producer 寫 episode-tasks 失敗 | |
| `DB_UNAVAILABLE` | 503 | HikariCP pool exhausted 或 connection refused | |
| `OBJECT_STORAGE_UNAVAILABLE` | 503 | S3 client 連線失敗（取 trajectory 時） | |
| `INFERENCE_SERVICE_TIMEOUT` | 504 | 005 同步呼叫超時（5 秒同步、60 秒 episode） | |
| `INTERNAL_ERROR` | 500 | 未分類 fallback | |
| `RATE_LIMITED` | 429 | （未來）per-user rate limit | |
| `VALIDATION_FAILED` | 422 | bean validation 拒絕（@Valid） | |

## 客戶端對應建議（給 007 React）

- 4xx：顯示錯誤訊息給使用者，不重試。
- 503/504：可重試 1-2 次（exponential backoff），仍失敗則顯示「服務暫時無法使用」。
- 401：清掉 JWT、跳轉登入頁。
- 403：UI 隱藏該功能或顯示「需 admin 權限」。

## Circuit breaker 行為（resilience4j）

當 005 連續失敗達到閾值（預設 50% 失敗率 over 10 calls）→ circuit OPEN：

- 30 秒內所有 `/api/v1/inference/*` 直接回 `INFERENCE_SERVICE_UNAVAILABLE` 503，不再呼叫 005（SC-003）。
- 30 秒後進 HALF_OPEN，放行 3 個試探請求；全成功 → CLOSED；任一失敗 → OPEN 再 30 秒。
- `/actuator/health` 之 `inferenceService` component 在 OPEN 時 status=DOWN。
