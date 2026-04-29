# Phase 1 Data Model: 003-ppo-training-env

**Status**: Complete
**Date**: 2026-04-29
**Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

本檔案定義 `PortfolioEnv` 的所有資料結構：輸入（從 002 / 001 讀入）、內部狀態、
觀測向量分區、動作向量、info dict、配置 dataclass。所有結構皆為 plan.md
Source Code 章節列出之 `src/portfolio_env/` 模組將實作的契約。

---

## §1 輸入資料 schema（從 002 / 001 讀入）

### §1.1 股票 OHLCV（從 `data_ingestion.loader.load_asset_snapshot`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| index | `pandas.DatetimeIndex` (UTC, daily) | 交易日 |
| `open`, `high`, `low`, `close` | `float64` | 已調整除權息（002 auto_adjust=True） |
| `volume` | `int64` | 成交量 |
| `quality_flag` | `category` | 取值 ∈ {ok, missing_close, zero_volume, duplicate_dropped}（002 FR-009） |

六檔資產：NVDA、AMD、TSM、MU、GLD、TLT。

### §1.2 FRED 利率（從 `data_ingestion.loader.load_rate_snapshot`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| index | `pandas.DatetimeIndex` (UTC, daily) | 日期 |
| `rate_pct` | `float64` | DTB3 年化利率（百分比）；後續轉日化使用 |
| `quality_flag` | `category` | 取值 ∈ {ok, missing_rate}（002 FR-009） |

### §1.3 SMC 特徵（從 `smc_features.batch_compute`）

接收 §1.1 的 OHLCV DataFrame，回傳擴增 5 欄（001 FR-001~004）：

| 欄位 | 型別 | 取值 | 說明 |
|---|---|---|---|
| `bos_signal` | `int8` | {-1, 0, 1} | 向下/無/向上突破 |
| `choch_signal` | `int8` | {-1, 0, 1} | 反向轉折訊號 |
| `fvg_distance_pct` | `float64` | ℝ ∪ {NaN} | 距最近未填補 FVG 的百分比；無 FVG 時為 NaN |
| `ob_touched` | `bool` | {True, False} | 當 K 線是否觸及最近 OB |
| `ob_distance_ratio` | `float64` | ℝ ∪ {NaN} | 距 OB 中心的 ATR 標準化距離 |

---

## §2 配置 dataclass

### §2.1 `RewardConfig`（frozen）

```python
@dataclass(frozen=True)
class RewardConfig:
    lambda_mdd: float = 1.0          # drawdown 權重
    lambda_turnover: float = 0.0015  # turnover 總權重（已涵蓋滑價）

    def __post_init__(self) -> None:
        if self.lambda_mdd < 0:
            raise ValueError("lambda_mdd must be >= 0")
        if self.lambda_turnover < 0:
            raise ValueError("lambda_turnover must be >= 0")
```

**不變式**：兩權重皆為非負；frozen 確保物件建立後不可變（Principle I）。

### §2.2 `PortfolioEnvConfig`（frozen）

```python
@dataclass(frozen=True)
class PortfolioEnvConfig:
    data_root: Path                  # 002 產出的 data/raw/ 路徑
    assets: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")
    include_smc: bool = True         # ablation 開關（FR-011）
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    position_cap: float = 0.4        # 單資產上限（FR-014c）
    base_slippage_bps: float = 5.0   # 市場模型常數（research R4，不入 reward 公式）
    initial_nav: float = 1.0
    start_date: date | None = None   # None = 資料起始日
    end_date: date | None = None     # None = 資料結束日
    smc_params: SMCParams = field(default_factory=SMCParams)  # 透傳給 001

    def __post_init__(self) -> None:
        if not (0 < self.position_cap <= 1):
            raise ValueError("position_cap must be in (0, 1]")
        if self.position_cap * len(self.assets) < 1.0:
            # 6 * 0.4 = 2.4 ≥ 1，OK；防止使用者把 cap 調太低導致無解
            raise ValueError("position_cap * num_assets must be >= 1")
        if self.initial_nav <= 0:
            raise ValueError("initial_nav must be > 0")
        if self.base_slippage_bps < 0:
            raise ValueError("base_slippage_bps must be >= 0")
```

**不變式**：`assets` 為 tuple（hashable，frozen 配套）；`position_cap × len(assets)`
≥ 1.0 確保 simplex 有解。

### §2.3 `SMCParams`（透傳，由 001 spec 規範）

不在本 feature 內定義；本 feature 只負責於 `__init__` 將其傳給
`smc_features.batch_compute(df, params=self.config.smc_params)`。

---

## §3 觀測向量分區（FR-010 / FR-011 / FR-010a 落地）

### §3.1 `include_smc=True` 時 D=63

| 索引範圍 | 維度 | 內容 | dtype 來源 |
|---|---|---|---|
| `[0:24]` | 24 | 6 資產 × 4 價格特徵 | float32（從 float64 cast） |
| `[24:54]` | 30 | 6 資產 × 5 SMC 特徵 | float32（離散值依 FR-010a 編碼） |
| `[54:56]` | 2 | macro：日化無風險利率、20d 利率變化 | float32 |
| `[56:63]` | 7 | 當前 weights（含 cash 為最後一維） | float32 |

#### §3.1.1 `[0:24]` 價格特徵子分區（每檔股票 4 維）

對每個資產 i ∈ {NVDA, AMD, TSM, MU, GLD, TLT} 在索引 `[4i : 4i+4]`：

| 偏移 | 名稱 | 公式 |
|---|---|---|
| 0 | `log_return_1d` | `log(close_t / close_{t-1})` |
| 1 | `log_return_5d` | `log(close_t / close_{t-5})` |
| 2 | `log_return_20d` | `log(close_t / close_{t-20})` |
| 3 | `volatility_20d` | `std(log_return_1d, window=20)` |

`t < 20` 時 backfill 用 `t=0` 的值（避免引入 NaN）。

#### §3.1.2 `[24:54]` SMC 特徵子分區（每檔股票 5 維）

對每個資產 i 在索引 `[24 + 5i : 24 + 5i + 5]`：

| 偏移 | 名稱（與 001 spec 一致）| 編碼（FR-010a） |
|---|---|---|
| 0 | `bos_signal` | int8 → float32 ∈ {-1.0, 0.0, 1.0} |
| 1 | `choch_signal` | int8 → float32 ∈ {-1.0, 0.0, 1.0} |
| 2 | `fvg_distance_pct` | float64 → float32；NaN → 0.0（FR-012） |
| 3 | `ob_touched` | bool → float32 ∈ {0.0, 1.0} |
| 4 | `ob_distance_ratio` | float64 → float32；NaN → 0.0（FR-012） |

#### §3.1.3 `[54:56]` macro 子分區

| 偏移 | 名稱 | 公式 |
|---|---|---|
| 0 | `risk_free_rate_daily` | `(1 + rate_pct/100)^(1/252) − 1` |
| 1 | `risk_free_rate_change_20d` | `risk_free_rate_daily_t − risk_free_rate_daily_{t-20}` |

#### §3.1.4 `[56:63]` weights 子分區

順序固定：`[NVDA, AMD, TSM, MU, GLD, TLT, CASH]`，與 action 順序一致（§4）。
首步（reset 後第一次 step）weights 為 `[1/7] * 7`（均分初始化），由 `reset()`
寫入。

### §3.2 `include_smc=False` 時 D=33

跳過 §3.1.2 整段；其他分區索引重編：

| 索引範圍 | 維度 | 內容 |
|---|---|---|
| `[0:24]` | 24 | 同 §3.1.1 |
| `[24:26]` | 2 | 同 §3.1.3 |
| `[26:33]` | 7 | 同 §3.1.4 |

---

## §4 動作向量

shape=(7,)、dtype=float32、`Box(low=0.0, high=1.0)`。

順序固定：`[NVDA, AMD, TSM, MU, GLD, TLT, CASH]`。

處理管線（FR-014）：
1. **NaN 檢查**：`if numpy.isnan(action).any(): raise ValueError("Action contains NaN")`
2. **L1 normalize**：
   - `s = action.sum()`
   - `if s < 1e-6: raise ValueError("Action sum near zero")`
   - `if abs(s − 1.0) > 1e-6: action_normalized = action / s`，標記 `info["action_renormalized"] = True`
   - 否則 `action_normalized = action`
3. **Position cap**：對任意 i，若 `action_normalized[i] > 0.4`：
   - `excess = action_normalized[i] − 0.4`
   - `action_normalized[i] = 0.4`
   - 將 `excess` 按其餘 6 維（不含被 cap 的 i）的當前權重比例分配
   - 重複至無 entry 超過 0.4（單次迭代最多 7 次必收斂）
   - 標記 `info["position_capped"] = True`
4. **寫入 next-step weights**：`self.current_weights = action_normalized`

---

## §5 內部狀態

`PortfolioEnv` 實例屬性：

| 屬性 | 型別 | 說明 |
|---|---|---|
| `self.config` | PortfolioEnvConfig | frozen 配置 |
| `self._trading_days` | `numpy.ndarray[date]` | 有效交易日序列（research R5 過濾後） |
| `self._closes` | `numpy.ndarray[float64]` | shape `(T, 6)`，已 align trading days |
| `self._returns` | `numpy.ndarray[float64]` | shape `(T, 6)`，next-day 報酬（用於 t→t+1 推進） |
| `self._smc_features` | `dict[str, ndarray[float32]]` 或 None | research R7 預計算結果；shape `(T, 5)` |
| `self._price_features` | `numpy.ndarray[float32]` | shape `(T, 24)`，§3.1.1 預計算 |
| `self._macro_features` | `numpy.ndarray[float32]` | shape `(T, 2)`，§3.1.3 預計算（含 forward fill） |
| `self._data_hashes` | `dict[str, str]` | research R6 結果 |
| `self.current_index` | int | 當前所在 trading day index（reset 後 = 0） |
| `self.current_weights` | `numpy.ndarray[float32]` | shape `(7,)`，初始 `[1/7] * 7` |
| `self.nav_history` | `list[float]` | 從 `initial_nav` 累積；長度 = `current_index + 1` |
| `self.peak_nav` | float | `max(nav_history)`；增量更新 |
| `self._skipped_dates` | `list[str]` | research R5 累積（reset 時清空） |
| `self._np_random` | `numpy.random.Generator` | research R1 |
| `self._py_random` | `random.Random` | research R1 |

---

## §6 `info` dict 結構

每步 `step()` 回傳的 `info` MUST 包含下列 key（其他 optional key 可加但不可移）：

| Key | 型別 | 說明 |
|---|---|---|
| `date` | str (ISO 8601) | 當前 trading day |
| `weights` | `list[float]` (len=7) | 當步處理後 weights（含 cash） |
| `nav` | float | 當前 NAV |
| `peak_nav` | float | 至今最高 NAV |
| `cash` | float | NAV × weights[6] |
| `asset_values` | `list[float]` (len=6) | NAV × weights[0:6] |
| `turnover` | float | `0.5 × sum(abs(w_t − w_{t-1}))` |
| `slippage_bps` | float | 等於 `config.base_slippage_bps × turnover`（純紀錄） |
| `reward_components` | dict | `{"log_return": float, "drawdown_penalty": float, "turnover_penalty": float}` |
| `action_raw` | `list[float]` (len=7) | step 輸入的原始 action |
| `action_processed` | `list[float]` (len=7) | 經 §4 三道處理後的 action |
| `action_renormalized` | bool | L1 normalize 是否觸發 |
| `position_capped` | bool | position cap 是否觸發 |
| `nan_replaced` | int | 累積 NaN→0.0 替換次數（FR-012） |
| `is_initial_step` | bool | `current_index == 1`（首次 step） |
| `data_hashes` | dict | `{asset_name: sha256_hex}`（每步同一物件） |
| `skipped_dates` | `list[str]` | 累積跳過日期 |

`info_to_json_safe(info)` 轉換規則：所有 `numpy.ndarray` → `list`，所有
`numpy.float32/float64` → `float`，所有 `numpy.int*` → `int`，`numpy.bool_` →
`bool`。完整 schema 由 `contracts/info-schema.json` 機器驗證。

---

## §7 不變式

下列不變式 MUST 由實作保證，並由 `tests/integration/` 與 `tests/contract/`
驗證：

1. **Reward 三項一致性**：`log_return − drawdown_penalty − turnover_penalty == reward`，
   容差 1e-9（FR-009、SC-004）。
2. **NAV 連續性**：`info["nav"]` 序列對任意 t ≥ 1 滿足
   `nav_t = nav_{t-1} × (1 + dot(weights_{t-1}, simple_returns_t))`，
   容差 1e-12（同機器）。
3. **Weights simplex**：`info["weights"]` 任一時刻 `sum(weights) == 1.0`（容差 1e-9）、
   `min(weights) >= 0`、`max(weights[0:6]) <= 0.4`（cash 不受 cap 限制）。
4. **Observation shape**：`include_smc=True` 時 `obs.shape == (63,)`；
   `include_smc=False` 時 `obs.shape == (33,)`；`obs.dtype == numpy.float32`。
5. **Episode 長度**：step 總次數 == `len(self._trading_days) - 1`（FR-016）。
6. **Hash 比對**：`__init__` 後 `self._data_hashes` 內容與 002 metadata
   完全一致（FR-021）。
7. **Seed 可重現**：兩次 `reset(seed=N)` 後執行相同 action 序列，trajectory
   byte-identical（SC-005）。
