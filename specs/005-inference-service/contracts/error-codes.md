# Error Codes: 推理服務

> **⚠️ SUPERSEDED — 2026-05-06**
> 本錯誤碼字典對應舊版 spec（multi-policy / episode replay 的錯誤類別）。
> spec.md 已於 2026-05-06 重寫為 C-lite，重新跑 `/speckit.plan` 時會生成新的錯誤碼字典。

統一錯誤回應 schema 與錯誤碼字典。對應 005-inference-service spec FR-014、data-model.md §9。

## Error Response 格式

所有非 2xx 回應 body 為：

```json
{
  "error": {
    "code": "<UPPER_SNAKE_CASE>",
    "message": "<human-readable, English>",
    "error_id": "<uuid4>",
    "details": { "...": "..." }
  }
}
```

- `code`: 大寫底線；下表枚舉。
- `message`: 不洩漏 stack trace、不洩漏 server 路徑。
- `error_id`: uuid4，與服務 stderr stack trace log 對應，運維可串接。
- `details`: 可選 object，提供結構化補充（例如 `expected: 63, got: 33`）；不放敏感資訊。

## 錯誤碼一覽

| Code | HTTP | 觸發條件 | message 範例 | details 欄位 |
|---|---|---|---|---|
| `OBSERVATION_DIM_MISMATCH` | 400 | request observation 長度 ≠ policy.obs_dim | `Expected obs dim 63, got 33` | `expected: int`, `got: int` |
| `OBSERVATION_NAN` | 400 | observation 含 NaN/Inf | `Observation contains NaN/Inf at index 12` | `index: int` |
| `INVALID_DATE_RANGE` | 400 | start_date >= end_date 或 dates 格式錯誤 | `start_date must be earlier than end_date` | `start: str`, `end: str` |
| `EPISODE_RANGE_TOO_LARGE` | 400 | end_date - start_date > episode_max_days | `Episode range 3650 days exceeds max 2920` | `requested_days: int`, `max_days: int` |
| `OBS_SMC_MISMATCH` | 400 | request include_smc 與 policy obs_dim 不符 | `policy obs_dim 33 requires include_smc=false` | `policy_obs_dim: int`, `requested_include_smc: bool` |
| `DATA_NOT_AVAILABLE` | 400 | 指定時間範圍超出 002 Parquet 快照覆蓋 | `Data range 2027-01-01 not in snapshot` | `available_start: date`, `available_end: date` |
| `POLICY_NOT_FOUND` | 404 | policy_id 不在 registry | `Policy 'baseline_seed1' not found` | `policy_id: str`, `available: list[str]` |
| `POLICY_ID_EXISTS` | 409 | POST /v1/policies/load 之 id 已存在 | `Policy id 'baseline_seed1' already loaded` | `policy_id: str` |
| `POLICY_LOAD_FAILED` | 400 | zip 檔不存在或讀取失敗 | `Cannot read policy at runs/.../final_policy.zip` | `policy_path: str`, `os_error: str` |
| `POLICY_FILE_CORRUPT` | 400 | zip 不是 sb3 PPO 格式 | `Not a valid stable-baselines3 PPO archive` | `policy_path: str` |
| `POLICY_METADATA_MISSING` | 400 | 同目錄無 metadata.json | `metadata.json not found beside policy zip` | `expected_path: str` |
| `INFERENCE_FAILED` | 500 | policy.predict 拋例外 | `Inference failed; see error_id in logs` | (空，stack trace 走 stderr) |
| `EPISODE_RUN_FAILED` | 500 | 003 env step 拋例外 | `Episode run failed at step 142; see error_id` | `step: int` |
| `SERVICE_NOT_READY` | 503 | 收到推理請求但 readyz 為 503 | `No policy loaded` | `policies_loaded: 0` |
| `INTERNAL_ERROR` | 500 | 未分類例外（fallback） | `Internal server error; see error_id` | (空) |

## 客戶端對應建議（給 006 Java client）

- HTTP 4xx → 不重試，將 `error_id` log 出方便後端 debug。
- HTTP 5xx + `INFERENCE_FAILED` / `EPISODE_RUN_FAILED` → 可重試 1 次（exponential backoff）。
- HTTP 503 + `SERVICE_NOT_READY` → 等候並重試（K8s rolling deploy 或 policy reload 過程）。
- HTTP 409 → 視為冪等：先 GET 確認狀態。

## 不在範圍

- 不提供 i18n（message 固定 English）。
- 不提供 RFC 7807 problem+json content-type（採自訂 `application/json`）。
