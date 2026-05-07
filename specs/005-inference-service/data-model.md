# Data Model: 推理服務（005-inference-service）— C-lite 版

**Last Major Revision**: 2026-05-06

定義服務內部資料結構、API request/response schema 與檔案系統佈局。所有 schema 為 Pydantic 2.x model（型別嚴格、自動 OpenAPI 對應）。

---

## 1. ServiceConfig — 啟動配置

`src/inference_service/config.py`，繼承 `pydantic_settings.BaseSettings`，啟動時驗證一次。

| Field | Type | Default | Source | 說明 |
|---|---|---|---|---|
| `policy_path` | `Path` | required | env `POLICY_PATH` | `final_policy.zip` 絕對路徑（image 內） |
| `data_root` | `Path` | `data/raw` | env `DATA_ROOT` | Parquet 目錄 |
| `redis_url` | `str` | required | env `REDIS_URL` | 例：`redis://redis:6379/0` |
| `schedule_cron` | `str` | `30 16 * * MON-FRI` | env `SCHEDULE_CRON` | crontab 格式（ET 時區固定） |
| `schedule_timezone` | `str` | `America/New_York` | env `SCHEDULE_TIMEZONE` | pytz timezone 字串 |
| `include_smc` | `bool` | `True` | env `INCLUDE_SMC` | 與訓練時對齊 |
| `seed` | `int` | `42` | env `SEED` | env reset seed |
| `redis_channel` | `str` | `predictions:latest` | env `REDIS_CHANNEL` | pub/sub channel name |
| `redis_key` | `str` | `predictions:latest` | env `REDIS_KEY` | latest cache key |
| `redis_ttl_seconds` | `int` | `604800` | env `REDIS_TTL_SECONDS` | 7 天 |
| `host` | `str` | `0.0.0.0` | env `HOST` | uvicorn bind |
| `port` | `int` | `8000` | env `PORT` | uvicorn bind |
| `log_level` | `str` | `INFO` | env `LOG_LEVEL` | stdlib logging level |

**驗證規則**：
- `policy_path` 必須存在且是 `.zip` 結尾，否則啟動失敗（exit 1）
- `data_root` 必須存在且至少有一個 `*.parquet` 檔
- `redis_url` 啟動時 ping 一次，連不上 exit 1
- `schedule_cron` 用 `apscheduler.triggers.cron.CronTrigger.from_crontab` 預先驗證

---

## 2. PredictionPayload — 推理輸出 schema

`src/inference_service/schemas.py`，Pydantic model。**99% 對齊 `predict.py` 既有 JSON 輸出**，僅新增 `triggered_by` 與 `inference_id`。

```python
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID

class TargetWeights(BaseModel):
    NVDA: float = Field(ge=0.0, le=1.0)
    AMD:  float = Field(ge=0.0, le=1.0)
    TSM:  float = Field(ge=0.0, le=1.0)
    MU:   float = Field(ge=0.0, le=1.0)
    GLD:  float = Field(ge=0.0, le=1.0)
    TLT:  float = Field(ge=0.0, le=1.0)
    CASH: float = Field(ge=0.0, le=1.0)

class PredictionContext(BaseModel):
    data_root: str
    include_smc: bool
    n_warmup_steps: int
    current_nav_at_as_of: float

class PredictionPayload(BaseModel):
    # 既有欄位（對齊 predict.py）
    as_of_date: str                              # ISO date "2026-05-04"
    next_trading_day_target: str                 # 描述字串
    policy_path: str
    deterministic: bool
    target_weights: TargetWeights
    weights_capped: bool
    renormalized: bool
    context: PredictionContext

    # 新增欄位（005 引入）
    triggered_by: Literal["scheduled", "manual"]
    inference_id: UUID                           # 每次 inference 一個 uuid4
    inferred_at_utc: str                         # ISO timestamp "2026-05-06T05:30:42.123Z"
```

**Contract invariant**：跑一次 `python -m ppo_training.predict --policy ... --as-of ...` 產出 JSON，與 `POST /infer/run` 同條件下產出 JSON，**除了** `triggered_by` / `inference_id` / `inferred_at_utc` 三個新欄位外，其他欄位 byte-identical。Phase 7 contract test 自動驗證。

---

## 3. HealthResponse — `/healthz` 回應

```python
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    uptime_seconds: int
    policy_loaded: bool
    redis_reachable: bool
    last_inference_at_utc: str | None        # 最近一次成功 inference 時間
    next_scheduled_run_utc: str | None       # 下一次 scheduled trigger 時間
```

**HTTP 狀態碼**：
- 200：`status == "ok"`（policy 已載入 + redis 可達）
- 503：`status == "degraded"`（policy 載入失敗或 redis 連不上）

---

## 4. ErrorResponse — 統一錯誤 schema

對應 spec FR-012（結構化 log）+ HTTP error body：

```python
class ErrorResponse(BaseModel):
    code: str                      # e.g., "INFERENCE_BUSY", "NO_PREDICTION_YET"
    message: str                   # 人類可讀訊息
    error_id: str                  # uuid4，對應 stderr stack trace
    timestamp_utc: str
```

詳細錯誤碼字典見 [contracts/error-codes.md](./contracts/error-codes.md)。

---

## 5. InferenceState — handler 內部狀態

非 HTTP schema，純內部結構（`handler.py` module-level）：

```python
@dataclass
class InferenceState:
    lock: asyncio.Lock                     # 互斥
    policy: stable_baselines3.PPO          # eager-loaded on startup
    env_factory: Callable[[], gym.Env]     # 每次 inference 重新 build env（不 cache，因 reset 內部狀態）
    last_inference_at_utc: datetime | None
    last_inference_id: UUID | None
    inference_count: int                   # 啟動以來成功次數
    inference_failure_count: int           # 啟動以來失敗次數
```

**Lifecycle**：
- 啟動：`InferenceState` 在 FastAPI lifespan startup 建立，`policy` eager load
- 每次 inference：`async with state.lock:` 包整段，更新計數器
- 關閉：lifespan shutdown 不需要清理（process kill 即可）

---

## 6. ScheduledRunRecord — scheduler 內部紀錄

非 HTTP schema：

```python
@dataclass
class ScheduledRunRecord:
    fired_at_utc: datetime
    succeeded: bool
    inference_id: UUID | None
    error_class: str | None        # 失敗時填，e.g., "ValueError"
    error_message: str | None
    duration_seconds: float
```

僅用於 stdout log，不對外暴露 endpoint。

---

## 7. 檔案系統佈局（runtime, container 內）

```text
/app/
├── pyproject.toml
├── src/
│   ├── inference_service/
│   ├── portfolio_env/
│   ├── ppo_training/
│   └── smc_features/
├── runs/
│   └── 20260506_004455_659b8eb_seed42/      # 由 build-arg 指定哪個 run
│       ├── final_policy.zip
│       └── metadata.json                     # （可選）給 future policy versioning 用
└── data/
    └── raw/
        ├── nvda_daily_*.parquet
        ├── amd_daily_*.parquet
        ├── ... (8 個資產)
        └── *.meta.json
```

**Build args**：`POLICY_RUN_ID=20260506_004455_659b8eb_seed42`，Dockerfile 透過 `COPY runs/${POLICY_RUN_ID}/final_policy.zip /app/runs/${POLICY_RUN_ID}/` 引入。

---

## 8. Redis 資料佈局

| Type | Key/Channel | Value | TTL | 用途 |
|---|---|---|---|---|
| String | `predictions:latest` | PredictionPayload JSON | 7 天 | `GET /infer/latest` 讀回 |
| Pub/Sub | `predictions:latest` | PredictionPayload JSON | N/A | 通知訂閱者（006 Spring Gateway） |

**注意**：key 與 channel 同名是刻意設計（語意一致：「最新一筆 prediction」）。

---

## 9. 不在資料模型內

- 不存歷史 prediction（要看歷史請查 `runs/<run_id>/prediction_*.json` git history）
- 不存 user / session（無 auth、無 multi-tenant）
- 不存 policy registry（單一 default policy）
- 不存 episode trajectory（屬 future）
- 不存 metrics 時序（不上 Prometheus）

---

## Schema Migration

- **2026-05-06 (current)**：新增 `triggered_by`、`inference_id`、`inferred_at_utc`；其他欄位完全沿用 `predict.py` schema
- 未來如需擴充 prediction 欄位（例如加 SMC 信號當下狀態），MUST 先回頭改 spec FR-006/007 → 通過 review → 才能改本 model
