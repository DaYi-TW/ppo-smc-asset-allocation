# Error Codes: Spring Gateway (C-lite v2)

統一錯誤回應 schema 與錯誤碼表。對應 spec FR-005、data-model.md §2.2。

## Error Response 格式

```json
{
  "error": "InferenceServiceUnavailable",
  "message": "Inference service /infer/run did not respond within 90s",
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "details": null
}
```

- `error`: enum 字串，見下表.
- `message`: 人類可讀描述；**MUST NOT** 含 stack trace 或內部實作細節（與 005 對齊）.
- `requestId`: UUID v4，與 log line 中的 `requestId` 一致；前端可附給後端 reproduce.
- `details`: 可選 dict（如 timeout 時帶 `attemptedTimeoutMs`、CORS 拒絕時帶 `origin`），無資訊時為 `null`.

## 錯誤碼字典

| Error code | HTTP status | 觸發條件 | 對應 005 error code |
|---|---|---|---|
| `InferenceServiceUnavailable` | 503 | 005 連線拒絕 / DNS 失敗 / 5xx | `INFERENCE_FAILED` |
| `InferenceTimeout` | 504 | 005 呼叫超過配置 timeout（90s for /run、5s for /latest、2s for /healthz） | — |
| `InferenceBusy` | 409 | 005 回 409 INFERENCE_BUSY 透傳 | `INFERENCE_BUSY` |
| `PredictionNotReady` | 404 | 005 /infer/latest 回 404 NO_PREDICTION_YET | `NO_PREDICTION_YET` |
| `RedisUnavailable` | 503 | Redis 連不上 + SSE 端點請求；REST 路徑不受影響 | `REDIS_UNREACHABLE` |
| `BadRequest` | 400 | 005 回 4xx（除 404/409） | — |
| `InternalServerError` | 500 | Gateway 自身 unhandled exception | — |

## 規範

- Gateway **不**新增 005 沒有的 error code；所有 5xx 透傳 005 結果，4xx 也透傳（除非 Gateway 自身 validation 失敗）.
- Error code 對應前端 i18n key（如 `errors.inferenceServiceUnavailable`）；前端負責翻譯 / 顯示策略.
- Gateway log（FR-012）對每個 error 寫一筆 JSON line，含 `errorClass`（exception class name）+ `requestId`，stderr stack trace 寫 logback rolling file（不洩漏給 client）.

## Out of scope

- 不做 retry-after header（C-lite 規模、客戶端自行處理）.
- 不做 ProblemDetail RFC 7807 格式（Spring 6 內建支援，但增加 schema 表面積；C-lite 用簡單 4 欄位 ErrorResponse）.
- 不做 multi-error aggregation（一次回多個 error）；每次回應只一個 error code.
