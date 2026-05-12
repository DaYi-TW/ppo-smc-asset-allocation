# Data Model: PPO Live Tracking Dashboard

**Feature**: 010-live-tracking-dashboard
**Created**: 2026-05-08
**Source**: spec.md Key Entities + research.md decisions

本文件枚舉 010 涉及的全部實體、欄位約束、關係、狀態轉移。Pydantic v2 strict mode (`extra='forbid'`)；TypeScript 由 OpenAPI codegen 產生（不手寫）。

---

## Entity index

| # | Entity | Persistence | Mutability | Schema source |
|---|--------|-------------|-----------|---------------|
| 1 | LiveTrackingArtefact | `runs/<policy_run_id>/live_tracking/live_tracking.json` | Mutable (append-only frames) | Reuse `EpisodeDetail` from 009 |
| 2 | LiveTrackingStatus | `runs/<policy_run_id>/live_tracking/live_tracking_status.json` | Mutable (overwrite) | New (本 feature) |
| 3 | DailyTrackerPipelineRun | In-memory (ephemeral) + log line | N/A | New (本 feature) |
| 4 | RefreshAcceptedResponse | HTTP 202 body | Immutable per request | New (本 feature) |
| 5 | EpisodeListItem | HTTP response (existing) | N/A | Reuse 009 + 加 `source` 欄位 |

---

## 1. LiveTrackingArtefact

**Path**: `runs/<policy_run_id>/live_tracking/live_tracking.json`

**Schema**: 完全沿用 009 `EpisodeDetail` Pydantic model（`src/inference_service/episode_schemas.py`）。**禁止**新增欄位、禁止改型別、禁止改 field order — 所有 OOS / Live 共享同一 DTO 是 SC-007 與 FR-014 的硬約束。

### Top-level fields (繼承 009)

```python
class EpisodeDetail(BaseModel):
    model_config = ConfigDict(extra='forbid')

    episode_id: str                    # FORMAT: "<policy_run_id>_live"
    policy_run_id: str                 # 同 OOS（指向 baked policy）
    seed: int                          # 沿用 OOS seed（reproducibility marker）
    horizon: int                       # = len(trajectoryInline) — pipeline 每次 refresh 重算
    summary: EpisodeSummary
    trajectoryInline: list[FrameRecord]  # APPEND-ONLY
    smcOverlay: SMCOverlay             # FULL RECOMPUTE per refresh
    perAssetOhlc: dict[str, list[OHLCBar]]  # APPEND-ONLY per asset
```

### 010 specific constraints

| Field | OOS 行為 | Live 行為 (010) | Enforcement |
|-------|----------|----------------|-------------|
| `episode_id` | `<timestamp>_<commit>_seed<n>` | `<policy_run_id>_live`（單一 live id 對應單一 policy） | FR-001, R5 |
| `horizon` | 固定（OOS 一次性建立） | 隨 frames 增加而變大 | FR-007 (append-only) |
| `trajectoryInline[*].step_index` | 0-based 連續 | 0-based 連續，新 frame 取 `prev_max + 1` | FR-007 |
| `trajectoryInline[*].t` (date string) | OOS 範圍 | 起點 `2026-04-29`, 終點 ≤ `today`，跳非交易日 | FR-002, FR-006 |
| `summary.finalNav` etc. | 一次性計算 | 每次 refresh 重算（不增量） | FR-005 |
| `smcOverlay` | 一次性計算 | 每次 refresh 全段重算（含已存在 frames） | FR-004 (R4) |

### Validation rules

1. **Append-only invariant**: `new_artefact.trajectoryInline[:len(old)] == old.trajectoryInline` byte-equal. Pipeline 不可改寫已存在 frame。
2. **Date monotonic**: `[f.t for f in trajectoryInline]` 嚴格遞增；連續 frames 的日期差必須是 NYSE 交易日步進（不限 1 天，因含周末/假期）。
3. **Schema parity with OOS**: Pydantic 解析 live_tracking.json 必須直接餵入 `EpisodeDetail.model_validate()` 不報錯。

### State transitions

```
[absent]
   │
   │ POST /refresh (first call, today >= 2026-04-29)
   ▼
[has 1+ frames, last_frame_date < today]
   │
   │ POST /refresh (already-up-to-date OR fill missing days)
   ▼
[has N+M frames, last_frame_date == today (or latest trading day)]
   │
   │ next trading day → POST /refresh
   ▼ (loop)
```

---

## 2. LiveTrackingStatus

**Path**: `runs/<policy_run_id>/live_tracking/live_tracking_status.json`

**Purpose**: persistent state across process restarts; 是 `GET /api/v1/episodes/live/status` 的資料源。

```python
class LiveTrackingStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')

    last_updated: datetime | None       # ISO 8601 UTC, e.g. "2026-05-08T14:00:00Z"
    last_frame_date: date | None        # YYYY-MM-DD; None when artefact 尚未建立
    is_running: bool                    # 當前是否有 pipeline 正在跑
    last_error: str | None              # 失敗訊息（含三類前綴 DATA_FETCH:/INFERENCE:/WRITE:）
    running_pid: int | None             # is_running=True 時必填，用於 orphan 偵測
    running_started_at: datetime | None # is_running=True 時必填，UTC

    # Computed (response only, not persisted)
    data_lag_days: int | None = None    # today (UTC date) - last_frame_date
```

### Validation rules

1. `is_running == True` ⇒ `running_pid is not None and running_started_at is not None`
2. `is_running == False` ⇒ `running_pid is None and running_started_at is None`
3. `last_updated` 採 UTC（避免時區歧義）；`last_frame_date` 採 NYSE 本地日期（與 OHLCV 來源一致）
4. `data_lag_days` 不持久化；read time 由 endpoint 計算 = `(today_utc - last_frame_date).days`，clamp ≥ 0

### State transitions

```
status.is_running:
  [False] ──POST /refresh accepted──▶ [True] ──pipeline finish──▶ [False, last_error=None, last_updated=now]
                                       │
                                       └──pipeline crash──▶ [False, last_error="...", last_updated unchanged]

status.is_running on startup recovery:
  [True, pid 不存在 OR pid 啟動時間 > running_started_at]
    ──reset──▶ [False, last_error="recovered from orphan lock"]
```

### Orphan recovery（R6）

App lifespan startup hook 執行：
1. 讀 `status.json`；若 `is_running == True`：
2. 呼叫 `psutil.pid_exists(running_pid)`；若不存在 ⇒ orphan，reset。
3. 若存在，比對 `psutil.Process(pid).create_time()` 與 `running_started_at`；若 process 啟動時間 ≠ status 紀錄 ⇒ orphan，reset。
4. Reset = 寫 `is_running=False, running_pid=None, running_started_at=None, last_error="orphan lock recovered at startup"`。

---

## 3. DailyTrackerPipelineRun

**Persistence**: 不持久化；run-time 物件 + 一條 structured log line。

```python
@dataclass
class DailyTrackerPipelineRun:
    pipeline_id: str               # uuid4，僅 log 用
    started_at: datetime           # UTC
    target_dates: list[date]       # 本次補齊的交易日 list
    frames_appended: int = 0
    smc_zones_computed: int = 0    # 新計算的 OB+FVG+swing+CHoCH/BOS 總數
    pipeline_duration_ms: float = 0.0
    final_status: Literal["success", "failed"] = "failed"
    error_class: str | None = None  # "DATA_FETCH" | "INFERENCE" | "WRITE" | None
    error_message: str | None = None
```

### Log line (FR-026, Constitution Principle IV)

完成或失敗時 emit JSON line via `structlog`:

```json
{
  "event": "daily_tracker_pipeline_complete",
  "pipeline_id": "...",
  "policy_run_id": "20260506_004455_659b8eb_seed42",
  "frames_appended": 3,
  "smc_zones_computed": 207,
  "pipeline_duration_ms": 1842.3,
  "final_status": "success",
  "error_class": null,
  "ts": "2026-05-08T14:00:01.842Z"
}
```

---

## 4. RefreshAcceptedResponse

**Endpoint**: `POST /api/v1/episodes/live/refresh` (202 path)

```python
class RefreshAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    accepted: Literal[True]
    pipeline_id: str
    estimated_duration_seconds: int  # >= 1
    poll_status_url: str             # = "/api/v1/episodes/live/status"
```

### 409 path

`Content-Type: application/json`，body:

```python
class RefreshConflictResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    detail: Literal["pipeline already running"]
    running_pid: int
    running_started_at: datetime
    poll_status_url: str
```

---

## 5. EpisodeListItem (modified)

**Source**: 009 `EpisodeListItem`，本 feature 加 `source` discriminator。

```python
class EpisodeListItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    episode_id: str
    policy_run_id: str
    seed: int
    horizon: int
    final_nav: float
    cum_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    source: Literal["oos", "live"]    # NEW (FR-013)
```

### Ordering rule (R5)

`GET /api/v1/episodes` 回傳順序：所有 `source == "oos"` 在前（依 episode_id 字典序），所有 `source == "live"` 在後。確保 OOS 學術 baseline 永遠是 list[0]。

---

## Cross-entity invariants

| Invariant | 涉及 entities | Test location |
|-----------|---------------|---------------|
| INV-1: live artefact 與 status 必須同步 — `len(trajectoryInline) > 0` ⇒ `status.last_frame_date == trajectoryInline[-1].t` | LiveTrackingArtefact + LiveTrackingStatus | `tests/integration/live_tracking/test_artefact_status_sync.py` |
| INV-2: pipeline 失敗時 artefact bytes 不變 | LiveTrackingArtefact + DailyTrackerPipelineRun | `tests/contract/live_tracking/test_atomic_rollback.py` |
| INV-3: append-only — 任意兩次 refresh 後 `new[:k] == old[:k]` | LiveTrackingArtefact | `tests/contract/live_tracking/test_append_only.py` (Constitution Principle I gate) |
| INV-4: reward parity — pipeline 寫入的 `reward.components` 必須等於 `PortfolioEnv.step()` 的 reward 三元 (1e-9 tol) | LiveTrackingArtefact + `src/ppo_training/env/reward.py` | `tests/contract/live_tracking/test_reward_parity.py` (Constitution Principle III gate) |
| INV-5: OOS hash stability — 重抓 5 次 OOS episode_detail.json sha256 全相等 | EpisodeDetail (OOS only) | `tests/contract/episode_artifact/test_oos_immutable_hash.py` (Constitution Principle I gate) |
| INV-6: status enumerated fields — response keys 集合 = `{last_updated, last_frame_date, data_lag_days, is_running, last_error}` (no extra) | LiveTrackingStatus | `tests/contract/live_tracking/test_status_schema.py` |

---

## Out-of-scope entities

以下不在 010 data model：
- 多 policy 並行 live tracking → 未來 feature。
- Cron schedule entity → 明確排除（OUT OF SCOPE）。
- 歷史 prediction 修訂記錄 → append-only 約束阻擋此需求。
