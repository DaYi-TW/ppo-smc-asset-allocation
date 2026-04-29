# Data Model: 推理服務（005-inference-service）

定義服務內部資料結構、API request/response schema 與檔案系統佈局。所有 schema 為 Pydantic 2.x model（型別嚴格、自動 OpenAPI 對應）。

## 1. 服務啟動配置（ServiceConfig）

`src/inference_service/config.py`，從環境變數讀取，啟動時驗證一次。

| Field | Type | Default | Source | 說明 |
|---|---|---|---|---|
| `default_policy_path` | `Path \| None` | None | env `INFERENCE_DEFAULT_POLICY_PATH` | 啟動載入的 policy zip；None 時 `/readyz` 503 |
| `default_policy_id` | `str` | `"default"` | env `INFERENCE_DEFAULT_POLICY_ID` | default policy 的 id alias |
| `data_root` | `Path` | `data/raw/` | env `INFERENCE_DATA_ROOT` | episode API 用的 Parquet 根目錄 |
| `host` | `str` | `0.0.0.0` | env `INFERENCE_HOST` | uvicorn bind |
| `port` | `int` | `8000` | env `INFERENCE_PORT` | uvicorn bind |
| `log_level` | `str` | `INFO` | env `LOG_LEVEL` | DEBUG/INFO/WARNING/ERROR |
| `episode_max_days` | `int` | `2920` | env | episode 區間上限（8 年 ≈ 2920 日），超過 reject |
| `episode_stream_chunk` | `int` | `10` | query param 預設 | SSE 每 N step 推送 |

### 驗證規則

- `default_policy_path` 若給定 MUST 存在且為檔案（啟動驗證、不存在亦不啟動失敗，僅 `/readyz` 不 ready）。
- `port` ∈ [1, 65535]。
- `log_level` ∈ {DEBUG, INFO, WARNING, ERROR}。

## 2. Policy 物件（PolicyHandle）

`src/inference_service/policies/handle.py`。常駐 RAM。

```python
@dataclass(frozen=False)
class PolicyHandle:
    policy_id: str                          # 唯一 alias
    policy: stable_baselines3.PPO           # 載入後的 sb3 instance
    obs_dim: int                            # 33 (no SMC) 或 63 (with SMC)
    action_dim: int                         # 固定 7
    metadata: PolicyMetadata                # 從 004 metadata.json 讀入
    loaded_at_utc: datetime                 # ISO 8601
    policy_path: Path                       # 來源 zip 絕對路徑
    inference_count: int                    # 自此 handle 載入後的推理次數（觀測用）
```

### PolicyMetadata（從 004 metadata.json 攜帶）

```python
class PolicyMetadata(BaseModel):
    run_id: str                             # 004 run_id
    git_commit_hash: str                    # 訓練時 commit
    git_dirty: bool
    seed: int
    total_timesteps: int
    final_mean_episode_return: float
    final_mean_drawdown: float
    final_mean_turnover: float
    package_versions: dict[str, str]
    data_hashes: dict[str, str]
    config_sha256: str
    warnings: list[str]
```

## 3. Policy Registry（記憶體狀態）

`src/inference_service/policies/registry.py`：單例，`dict[str, PolicyHandle]`。

### 操作

- `register(handle: PolicyHandle) -> None`：`policy_id` 重複 raise `PolicyIdExistsError`（→ HTTP 409）。
- `unregister(policy_id: str) -> None`：不存在 raise `PolicyNotFoundError`（→ HTTP 404）。
- `get(policy_id: str | None) -> PolicyHandle`：None 用 default；不存在 raise。
- `list_ids() -> list[str]`：依載入順序。
- `count() -> int`：給 `/metrics` 與 `/readyz`。

### 不變量

- 同一 `policy_id` 全程唯一；要更換需先 DELETE 再 POST load。
- Default policy 卸載後 `/readyz` 必 503，直到任一 policy 載入。

## 4. API Schema — `/v1/infer`

### Request

```python
class InferenceRequest(BaseModel):
    observation: list[float]                # 33 或 63 維（依 policy）
    policy_id: str | None = None            # None 用 default
    deterministic: bool = False
```

### Response

```python
class InferenceResponse(BaseModel):
    inference_id: str                       # uuid4
    policy_id: str                          # 實際使用的 policy
    action: list[float]                     # 長度 7、sum=1、各維 ∈ [0, 0.4]（cash 不受 cap）
    value: float
    log_prob: float
    reward_components_estimate: RewardComponents | None  # 若 model 有 reward predictor
    latency_ms: float
    server_utc: str                         # ISO 8601 處理時間
```

```python
class RewardComponents(BaseModel):
    log_return: float
    drawdown_penalty: float
    turnover_penalty: float
    total: float
```

### 驗證規則

- `observation` 長度 MUST == `policy.obs_dim`，否則 HTTP 400 `OBSERVATION_DIM_MISMATCH`。
- `observation` 任一元素為 NaN/Inf MUST HTTP 400 `OBSERVATION_NAN`。
- `action` 由 003 action pipeline 計算，回傳已合法（FR-002）。

## 5. API Schema — `/v1/episode/run`

### Request

```python
class EpisodeRequest(BaseModel):
    policy_id: str | None = None
    start_date: date                        # ISO 8601
    end_date: date                          # 必 > start_date
    include_smc: bool = True                # 必須與 policy obs_dim 對齊
    seed: int | None = None                 # None → 用 policy 預設或 0
    deterministic: bool = True              # 預設 production 推理
```

### Response

```python
class EpisodeResponse(BaseModel):
    episode_id: str                         # uuid4
    policy_id: str
    start_date: date
    end_date: date
    num_steps: int
    episode_log: list[EpisodeLogEntry]      # 長度 == num_steps
    episode_summary: EpisodeSummary
    elapsed_seconds: float
```

### EpisodeLogEntry（與 003 info-schema.json 對齊）

```python
class EpisodeLogEntry(BaseModel):
    step: int
    date: date
    weights_target: list[float]             # action（pre-execution）
    weights_actual: list[float]             # post-execution（含 cap, normalize）
    nav: float
    log_return: float
    drawdown: float
    drawdown_penalty: float
    turnover: float
    turnover_penalty: float
    reward: float
    smc_signals: dict[str, float] | None    # 若 include_smc=True
    risk_free_rate: float
```

### EpisodeSummary

```python
class EpisodeSummary(BaseModel):
    final_nav: float
    peak_nav: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    total_return: float
    annualized_return: float
    annualized_volatility: float
    num_trades: int                          # weight change > 1e-6 的步數
    avg_turnover: float
```

### 驗證規則

- `end_date - start_date` 換算交易日 ≤ `episode_max_days`（預設 8 年），超過 HTTP 400 `EPISODE_RANGE_TOO_LARGE`。
- `include_smc` 與 policy `obs_dim` 不符 HTTP 400 `OBS_SMC_MISMATCH`。
- `start_date < end_date` 否則 HTTP 400 `INVALID_DATE_RANGE`。

## 6. API Schema — `/v1/episode/stream`

### Request

同 `/v1/episode/run`，但走 SSE。Query param `step_chunk` 控制每幾步推一次（預設 10）。

### Stream events

每筆事件格式：

```text
event: progress
id: <step>
data: {"step": 100, "total_steps": 252, "weights": [...], "nav": 1.082, "drawdown": 0.03}

event: done
id: final
data: {"episode_summary": {...}, "elapsed_seconds": 4.2}

event: error
id: error
data: {"error": {"code": "...", "message": "..."}}
```

## 7. API Schema — `/v1/policies`

### `GET /v1/policies` Response

```python
class PolicyListResponse(BaseModel):
    policies: list[PolicyInfo]
    default_policy_id: str | None

class PolicyInfo(BaseModel):
    policy_id: str
    obs_dim: int
    action_dim: int
    loaded_at_utc: str
    policy_path: str
    metadata: PolicyMetadata
    inference_count: int
```

### `POST /v1/policies/load` Request

```python
class PolicyLoadRequest(BaseModel):
    policy_path: str                        # 檔案系統路徑 or s3:// URI
    policy_id: str                          # 字母+數字+_-，[a-zA-Z0-9_-]{1,64}
    set_as_default: bool = False
```

### `POST /v1/policies/load` Response

`PolicyInfo`（同上）。

### `DELETE /v1/policies/{policy_id}` Response

```python
class PolicyDeleteResponse(BaseModel):
    policy_id: str
    deleted_at_utc: str
    remaining_count: int
```

## 8. API Schema — 健康/可觀測

### `GET /healthz` Response

```python
class HealthResponse(BaseModel):
    status: Literal["ok"]
    uptime_seconds: int
    server_utc: str
```

### `GET /readyz` Response

```python
class ReadyResponse(BaseModel):
    status: Literal["ready", "no_policy_loaded"]
    policies_loaded: int
```

HTTP 200 if `ready`、503 if `no_policy_loaded`。

### `GET /metrics` Response

`text/plain; version=0.0.4` Prometheus exposition format（非 JSON），由 prometheus-client 自動產生。

#### 指標清單

| 名稱 | 類型 | Labels | 說明 |
|---|---|---|---|
| `inference_requests_total` | Counter | `status`, `policy_id` | 總推理次數，status ∈ {success, error_4xx, error_5xx} |
| `inference_latency_seconds` | Histogram | `policy_id` | 推理延遲分佈 |
| `episode_requests_total` | Counter | `status` | episode API 總數 |
| `episode_latency_seconds` | Histogram | — | episode API 延遲 |
| `policies_loaded_count` | Gauge | — | 當前載入 policy 數 |
| `policy_load_duration_seconds` | Histogram | — | 動態載入耗時 |
| `process_resident_memory_bytes` | Gauge | — | 由 prometheus-client 自動 |
| `process_cpu_seconds_total` | Counter | — | 由 prometheus-client 自動 |

## 9. 錯誤回應 schema

統一格式（FR-014 + R10）：

```python
class ErrorBody(BaseModel):
    code: str                               # 大寫_底線
    message: str                            # 人類可讀
    error_id: str                           # uuid4
    details: dict[str, Any] | None = None

class ErrorResponse(BaseModel):
    error: ErrorBody
```

錯誤碼字典於 `contracts/error-codes.md`，至少含：

- `OBSERVATION_DIM_MISMATCH` (400)
- `OBSERVATION_NAN` (400)
- `INVALID_DATE_RANGE` (400)
- `EPISODE_RANGE_TOO_LARGE` (400)
- `OBS_SMC_MISMATCH` (400)
- `POLICY_NOT_FOUND` (404)
- `POLICY_ID_EXISTS` (409)
- `POLICY_LOAD_FAILED` (400)
- `POLICY_FILE_CORRUPT` (400)
- `INFERENCE_FAILED` (500)
- `SERVICE_NOT_READY` (503)

## 10. 不變量（Invariants）

1. `PolicyRegistry` 中任意 PolicyHandle 之 `obs_dim` ∈ {33, 63}、`action_dim == 7`。
2. 任意 `InferenceResponse.action` 長度 == 7、sum ≈ 1.0（容差 1e-9）、各維 ∈ [0, 0.4] 但 cash 維（idx 0）不受 cap。
3. `EpisodeResponse.episode_log` 長度 == `num_steps` == `EpisodeSummary.num_steps`。
4. `policy_id` 對應同一 PolicyHandle 全程唯一；DELETE 後可重新 POST 同 id。
5. 推理路徑無亂數；`deterministic=True` + 同 obs + 同 policy → action byte-identical（容差 0.0）。
6. Episode 路徑 `seed` 控制 env reset；同 seed + 同參數 + 同 policy → episode_log byte-identical。
7. 服務 stateless：除 `PolicyRegistry` 與 metric counter 外無其他 mutable state；重啟後 metric reset、registry 重新 load default。
