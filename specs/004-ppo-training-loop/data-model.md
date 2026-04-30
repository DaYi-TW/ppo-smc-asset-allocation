# Data Model: PPO Training Loop

## 1. TrainingConfig（dataclass）

對應 yaml 配置；驗證後反序列化為 frozen dataclass。

```python
@dataclass(frozen=True)
class EnvConfig:
    """對應 003 PortfolioEnvConfig 全部欄位之子集。"""
    data_root: str           # e.g. "data/raw"
    symbols: tuple[str, ...] # e.g. ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")
    start_date: str          # ISO 8601, e.g. "2018-01-01"
    end_date: str            # ISO 8601
    include_smc: bool        # ablation 開關
    position_cap: float      # 預設 0.4
    transaction_cost_bps: float  # 預設 5.0
    initial_cash: float      # 預設 1.0

@dataclass(frozen=True)
class PpoConfig:
    learning_rate: float        # 預設 3e-4
    n_steps: int                # 預設 2048
    batch_size: int             # 預設 64
    n_epochs: int               # 預設 10
    gamma: float                # 預設 0.99
    gae_lambda: float           # 預設 0.95
    clip_range: float           # 預設 0.2
    ent_coef: float             # 預設 0.0
    vf_coef: float              # 預設 0.5
    max_grad_norm: float        # 預設 0.5
    policy_kwargs: dict         # e.g. {"net_arch": [64, 64]}

@dataclass(frozen=True)
class TrainingMetaConfig:
    total_timesteps: int            # 預設 100000
    seed: int                       # 必填
    checkpoint_freq: int            # 預設 50000
    eval_freq: int                  # 預設 10000
    device: Literal["cpu", "cuda", "auto"]
    log_dir: str                    # 預設 "runs/"

@dataclass(frozen=True)
class LoggingConfig:
    tensorboard: bool               # 預設 True
    wandb_project: str | None       # 預設 None
    metrics_csv_freq: int           # 預設 1000

@dataclass(frozen=True)
class ExpectedDataHashes:
    """資料快照 hash gate（FR-019）。"""
    NVDA: str | None
    AMD: str | None
    TSM: str | None
    MU: str | None
    GLD: str | None
    TLT: str | None
    DTB3: str | None  # FRED 利率序列

@dataclass(frozen=True)
class ExpectedVersions:
    """套件版本 gate（FR-018）。"""
    numpy: str | None
    pandas: str | None
    gymnasium: str | None
    stable_baselines3: str | None
    torch: str | None

@dataclass(frozen=True)
class TrainingConfig:
    env: EnvConfig
    ppo: PpoConfig
    training: TrainingMetaConfig
    logging: LoggingConfig
    expected_data_hashes: ExpectedDataHashes | None
    expected_versions: ExpectedVersions | None
```

**驗證規則**（額外於 JSON Schema 之外）:

- `training.total_timesteps` 必須為 `n_steps` 的整數倍（PPO 要求）。
- `training.checkpoint_freq` 必須 ≥ `n_steps` 且為其整數倍。
- `env.symbols` 之每個 ticker 必須在 `data_root` 下有對應 Parquet 檔。
- `ppo.batch_size` 必須整除 `n_steps`。

---

## 2. TrainingArtefacts

對應 `runs/<UTC_timestamp>_<git_hash>_seed<N>/` 目錄結構。

```text
runs/20260429_141523_a0acd02_seed1/
├── config.yaml             # resolved config (含預設值展開)
├── final_policy.zip        # sb3 PPO checkpoint
├── checkpoint_step_50000.zip
├── checkpoint_step_100000.zip  # = final_policy.zip 之硬連結
├── replay_buffer.pkl       # rollout buffer 最終狀態
├── prng_state.pkl          # 4 層 PRNG 狀態 snapshot
├── tensorboard/
│   └── events.out.tfevents.*
├── metrics.csv             # FR-010
├── metadata.json           # FR-008, schema-validated
├── stdout.log
└── stderr.log
```

**run 目錄命名規約**:

- 格式：`<UTC_timestamp>_<git_hash7>_seed<N>`
- `UTC_timestamp` 格式 `YYYYMMDD_HHMMSS`
- `git_hash7` 取 `git rev-parse --short=7 HEAD`；若 `git diff --quiet` 為 false（dirty），追加 `-dirty`
- `N` 為 seed 整數值

---

## 3. MetricsRow

`metrics.csv` 一列，13 個欄位（FR-010）：

| 欄位 | 型別 | 描述 |
|---|---|---|
| `step` | int | 累積 timesteps（含跨 rollout） |
| `mean_episode_return` | float | 過去 100 個完成 episode 之 return 平均 |
| `mean_episode_length` | int | 過去 100 個完成 episode 之長度平均 |
| `mean_log_return` | float | reward 第 1 項分量平均（每 episode 內取均） |
| `mean_drawdown_penalty` | float | reward 第 2 項分量平均 |
| `mean_turnover_penalty` | float | reward 第 3 項分量平均 |
| `policy_loss` | float | sb3 PPO logger `train/policy_gradient_loss` |
| `value_loss` | float | sb3 PPO logger `train/value_loss` |
| `entropy` | float | sb3 PPO logger `train/entropy_loss` |
| `approx_kl` | float | sb3 PPO logger `train/approx_kl` |
| `explained_variance` | float | sb3 PPO logger `train/explained_variance` |
| `learning_rate` | float | 當前 LR（含 schedule 套用後） |
| `fps` | float | 平均 frames-per-second（自啟動） |

**寫出格式**（FR-009）: `pandas.to_csv(float_format='%.18g', lineterminator='\n', index=False)`。

---

## 4. TrainingMetadata（metadata.json）

對應 `contracts/training-metadata.schema.json`（FR-008、FR-022）。

```python
@dataclass(frozen=True)
class TrainingMetadata:
    # 識別
    run_id: str                     # = run 目錄名
    seed: int
    git_commit_hash: str            # 完整 40 字元
    git_dirty: bool

    # 時序
    utc_start: str                  # ISO 8601 with 'Z'
    utc_end: str
    duration_seconds: float

    # 環境
    hostname: str
    python_version: str             # e.g. "3.11.7"
    package_versions: dict[str, str]
    device: str                     # "cpu" | "cuda:0" | ...
    cuda_capability: str | None     # e.g. "8.0"

    # 資料指紋
    data_hashes: dict[str, str]     # {asset: sha256_hex}, lowercase, 64 chars

    # 訓練結果
    total_timesteps: int
    final_mean_episode_return: float
    final_mean_drawdown: float
    final_mean_turnover: float

    # 異常
    abort_reason: str | None        # null 表示正常結束
    warnings: list[str]             # e.g. ["degenerate_run"]

    # 配置指紋
    config_sha256: str              # resolved config.yaml 之 hash
```

**驗證**: 由 `contracts/training-metadata.schema.json` JSON Schema 驗證。

---

## 5. AggregateReport

多 seed 結束後產出，路徑 `runs/aggregate_<config_name>_<UTC_timestamp>/`。

```text
runs/aggregate_baseline_20260429_150000/
├── aggregate.csv       # mean/std/min/max/ci95 per metric per step
├── aggregate.png       # learning curve with mean ± std band
├── metadata_aggregate.json  # 各 seed run_id、聚合方法、scipy version
└── compare.csv         # 若提供 --compare-baseline 才產出
```

**`aggregate.csv` 欄位**: `step` + `mean_*` × 12 + `std_*` × 12 + `min_*` × 12 + `max_*` × 12 + `ci95_lower_*` × 12 + `ci95_upper_*` × 12（共 73 欄）。

**`metadata_aggregate.json`**:

```python
@dataclass(frozen=True)
class AggregateMetadata:
    config_name: str
    seeds: list[int]
    run_ids: list[str]
    n_seeds: int
    final_mean_return_mean: float
    final_mean_return_std: float
    final_mean_return_cv: float    # CV = std / |mean|
    final_mean_return_ci95: tuple[float, float]
    aggregate_utc: str
    scipy_version: str
    welch_ttest_p_value: float | None  # 若 --compare-baseline 才填
    cohens_d: float | None
```

---

## 6. Internal Types

### `RunPaths`

```python
@dataclass(frozen=True)
class RunPaths:
    root: pathlib.Path             # runs/<run_id>/
    config: pathlib.Path           # root / "config.yaml"
    final_policy: pathlib.Path     # root / "final_policy.zip"
    metrics_csv: pathlib.Path      # root / "metrics.csv"
    metadata_json: pathlib.Path    # root / "metadata.json"
    tensorboard_dir: pathlib.Path  # root / "tensorboard"
    stdout_log: pathlib.Path
    stderr_log: pathlib.Path
```

### `PRNGState`（用於 `--resume`）

```python
@dataclass(frozen=True)
class PRNGState:
    python_random_state: tuple
    numpy_random_state: dict        # np.random.get_state() 回傳之 dict
    torch_random_state: bytes       # torch.random.get_rng_state()
    torch_cuda_random_state: list[bytes] | None
    gymnasium_env_state: dict       # 由 003 env 提供
```

序列化採 `pickle`（檔名 `prng_state.pkl`）。

---

## 7. State Transitions

### Trainer 狀態機

```
INIT
  ├─→ DATA_GATE_PASSED  (資料 hash + 套件版本驗證)
  │     └─→ ENV_BUILT  (003 PortfolioEnv 建構)
  │           └─→ MODEL_BUILT  (sb3 PPO 建構，支援 --resume 載入)
  │                 └─→ TRAINING  (sb3 model.learn() 執行)
  │                       ├─→ COMPLETED  (達到 total_timesteps)
  │                       │     └─→ ARTEFACTS_WRITTEN
  │                       └─→ ABORTED   (NaN loss / SIGINT / disk full)
  │                             └─→ ARTEFACTS_WRITTEN with abort_reason
  └─→ DATA_GATE_FAILED  (raise，不進入後續)
```

**保證**: `ARTEFACTS_WRITTEN` 為 atomic — 寫入時透過 `tempfile.NamedTemporaryFile` + `os.replace()`，避免半損 artefact（spec edge case）。

---

## 8. JSON Schema 對應

- `contracts/training-config.schema.json` 對應 §1 TrainingConfig
- `contracts/training-metadata.schema.json` 對應 §4 TrainingMetadata
- `contracts/cli.md` 描述 CLI 介面（非 JSON Schema，採 markdown 表格）

---

## 9. 不變量（Invariants）

- I1: 每個 run 目錄之 `config.yaml` 為 resolved（含全部預設值展開）；不依賴啟動時的 ambient 預設。
- I2: `metrics.csv` 之 `step` 嚴格遞增、首列為 `metrics_csv_freq`、step 間隔均為 `metrics_csv_freq`。
- I3: `final_policy.zip` 必存在（即使 abort）；若 abort，policy 為最後 checkpoint 的副本。
- I4: `metadata.json` 之 `data_hashes` 全部小寫 64 字元 hex（SHA-256）。
- I5: 同一 `seed`、同一 `git_commit_hash`、同一 `config_sha256` 下，`metrics.csv` byte-identical（SC-003）。
