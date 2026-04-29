# Phase 1 Data Model: 001-smc-feature-engine

**Date**: 2026-04-29
**Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md)
**Plan**: [plan.md](./plan.md)

定義本 feature 涉及的所有資料結構：輸入/輸出 DataFrame schema、特徵參數、增量狀態
物件、與內部中介概念。所有結構為實作指引，最終以 Python type stubs 與 dataclass
具體化於 `src/smc_features/types.py`。

---

## 1. Input Schema：OHLCV DataFrame

**用途**：`batch_compute` 與 `incremental_compute` 的主輸入。由呼叫方提供，本 feature
不負責資料抓取（範圍邊界，spec FR 範圍排除）。

| 欄位 | dtype | 必要 | 說明 |
|---|---|---|---|
| `open` | `float64` | ✅ | 開盤價，已除權息調整（與 feature 002 輸出一致） |
| `high` | `float64` | ✅ | 最高價 |
| `low` | `float64` | ✅ | 最低價 |
| `close` | `float64` | ✅ | 收盤價 |
| `volume` | `float64` 或 `int64` | ✅ | 成交量；零值代表停牌（spec FR-014） |
| `quality_flag` | `object`（str） | ⚪ | 來自 feature 002，值 ∈ {"ok", "missing_close", "zero_volume", "missing_rate", "duplicate_dropped"}。若呼叫方未提供，本 feature 視為全 "ok" |

**Index**：`pandas.DatetimeIndex`（無時區或 UTC，需單調遞增、無重複）。

**驗證規則**：
- `df.index.is_monotonic_increasing` MUST 為 `True`，否則 `ValueError`（spec FR-013）。
- `df.index.is_unique` MUST 為 `True`。
- 必要欄位存在性檢查；缺漏拋 `KeyError` 並列出缺少欄位（spec FR-012）。

---

## 2. Output Schema：Feature-Augmented DataFrame

**用途**：`batch_compute` 的回傳值。在 input DataFrame 上新增特徵欄位，列數與 index
完全保留（spec FR-001、FR-014）。

| 欄位 | dtype | 值域 | 說明 |
|---|---|---|---|
| `bos_signal` | `int8` | {-1, 0, 1} | 市場結構斷裂：+1 向上、0 無、-1 向下 |
| `choch_signal` | `int8` | {-1, 0, 1} | 性格轉變（衝突時優先於 BOS，spec FR-019） |
| `fvg_distance_pct` | `float64` | (-∞, +∞) ∪ {NaN} | 距最近未填補 FVG midpoint 的帶符號百分比 |
| `ob_touched` | `bool` | True/False | 當前 K 棒是否觸碰最近有效 OB |
| `ob_distance_ratio` | `float64` | (-∞, +∞) ∪ {NaN} | 收盤距 OB midpoint 的 ATR 標準化距離 |

**附加（可選）視覺化輔助欄位**（非必要，由 `batch_compute(..., include_aux=True)` 啟用）：

| 欄位 | dtype | 說明 |
|---|---|---|
| `swing_high_marker` | `bool` | 此列是否為確認的 swing high |
| `swing_low_marker` | `bool` | 此列是否為確認的 swing low |
| `fvg_top_active` | `float64` | 當前最近未填補 FVG 的 top（無則 NaN） |
| `fvg_bottom_active` | `float64` | 當前最近未填補 FVG 的 bottom |
| `ob_top_active` | `float64` | 當前最近有效 OB 的 top |
| `ob_bottom_active` | `float64` | 當前最近有效 OB 的 bottom |

**NaN 政策**：對 `quality_flag != "ok"` 的列、或視窗未就緒的列（前 `swing_length` 根
無法判定 swing），所有特徵欄位輸出 `NaN`（int 欄位則為 `pd.NA` 並轉為 `Int8` nullable
dtype）。詳細規則見 spec FR-014、FR-015。

---

## 3. Feature Parameters：`SMCFeatureParams`

**用途**：呼叫方顯式傳入的判定參數（spec FR-017）。為 frozen dataclass。

```python
@dataclass(frozen=True)
class SMCFeatureParams:
    swing_length: int = 5           # R1: swing high/low 偵測視窗（左右各 L 根）
    fvg_min_pct: float = 0.001       # R2: FVG 最小幅度（相對中間 K 棒收盤）
    ob_lookback_bars: int = 50       # R3: OB 時間失效視窗
    atr_window: int = 14             # R3: ATR 標準化視窗（Wilder's smoothing）
```

**驗證規則**：
- `swing_length >= 1`、`fvg_min_pct >= 0`、`ob_lookback_bars >= 1`、`atr_window >= 1`。
- 違反時建構階段拋 `ValueError`。

---

## 4. Internal Entities

### 4.1 `SwingPoint`

```python
@dataclass(frozen=True)
class SwingPoint:
    timestamp: pd.Timestamp
    price: float                    # high for swing_high; low for swing_low
    kind: Literal["high", "low"]
    bar_index: int                  # 在原 DataFrame 的位置（0-based）
```

**生命週期**：在前 `swing_length` 根 K 棒後才能 *確認*，故 swing point 在資料末段
有 `swing_length` 根延遲（research R1）。

### 4.2 `FVG`（Fair Value Gap）

```python
@dataclass(frozen=True)
class FVG:
    formation_timestamp: pd.Timestamp  # 中間 K 棒的 timestamp（i-1）
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float                          # 上緣
    bottom: float                       # 下緣
    is_filled: bool                     # 是否已被完全填補
    fill_timestamp: Optional[pd.Timestamp]   # 填補時間（未填補為 None）
```

**狀態轉移**：`is_filled = False` → `True`（單向，一旦填補不可復原）。research R2 定義
完全填補條件。

### 4.3 `OrderBlock`

```python
@dataclass(frozen=True)
class OrderBlock:
    formation_timestamp: pd.Timestamp
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float                          # K 棒 high
    bottom: float                       # K 棒 low
    midpoint: float                     # (top + bottom) / 2
    expiry_bar_index: int               # formation + ob_lookback_bars
    invalidated: bool                   # 結構失效旗標
    invalidation_timestamp: Optional[pd.Timestamp]
```

**有效判定**：`active = (not invalidated) and (current_bar_index <= expiry_bar_index)`。
research R3 定義時間失效與結構失效兩條件。

---

## 5. Engine State：`SMCEngineState`

**用途**：增量模式的中介狀態（research R6）。為 frozen dataclass，每次 `incremental_compute`
回傳新 instance。

```python
@dataclass(frozen=True)
class SMCEngineState:
    # Swing 結構
    last_swing_high: Optional[SwingPoint]
    last_swing_low: Optional[SwingPoint]
    prev_swing_high: Optional[SwingPoint]
    prev_swing_low: Optional[SwingPoint]
    trend_state: Literal["bullish", "bearish", "neutral"]

    # FVG / OB 列表
    open_fvgs: tuple[FVG, ...]            # 未填補 FVG（按形成時間升序）
    active_obs: tuple[OrderBlock, ...]    # 有效 OB（按形成時間升序）

    # ATR 緩衝
    atr_buffer: tuple[float, ...]          # 最近 atr_window 個 TR 值
    last_atr: Optional[float]              # 最近一次計算的 ATR

    # 計數
    bar_count: int                          # 已處理 K 棒總數

    # 不變參數快照（保證 batch / incremental 一致）
    params: SMCFeatureParams
```

**初始狀態**（`bar_count == 0`）：所有 Optional 欄位為 `None`、tuple 欄位為 `()`、
`trend_state == "neutral"`。

**State 由 `batch_compute` 順帶輸出**：`batch_compute` 不僅回傳特徵 DataFrame，亦
回傳對應「處理完最後一根 K 棒後」的 `SMCEngineState`，供使用者後續切換到增量模式
（contracts 規範詳見 `contracts/api.pyi`）。

---

## 6. Feature Row（單列輸出，增量模式）

```python
@dataclass(frozen=True)
class FeatureRow:
    timestamp: pd.Timestamp
    bos_signal: int                  # -1, 0, 1
    choch_signal: int
    fvg_distance_pct: float          # NaN if none
    ob_touched: bool
    ob_distance_ratio: float
    # aux 欄位（可選，與 batch include_aux 對稱）
    swing_high_marker: Optional[bool] = None
    swing_low_marker: Optional[bool] = None
    fvg_top_active: Optional[float] = None
    fvg_bottom_active: Optional[float] = None
    ob_top_active: Optional[float] = None
    ob_bottom_active: Optional[float] = None
```

`incremental_compute` 回傳 `tuple[FeatureRow, SMCEngineState]`。

---

## 7. Visualization Inputs

`visualize()` 接收下列輸入（不引入新實體，皆為前述結構或 primitive）：

- `df`: 含 OHLCV 與特徵欄位的 DataFrame（即 `batch_compute` 的輸出）
- `time_range`: `tuple[pd.Timestamp, pd.Timestamp]`（含起訖）
- `output_path`: `Path | str`
- `format`: `Literal["png", "html"]`
- `params`（可選）: `SMCFeatureParams`，用於圖例註腳顯示參數值

---

## 8. Cross-Feature Schema Compatibility

與 feature 002（資料抓取）的接口契約：

| 002 輸出欄位 | 本 feature 視為 |
|---|---|
| `open`, `high`, `low`, `close`, `volume` | 直接使用（dtype 完全相容） |
| `quality_flag == "ok"` | 正常處理 |
| `quality_flag != "ok"` | 該列特徵輸出 NaN（spec FR-014），且不參與下游列的視窗計算（spec FR-015） |
| `index`（datetime） | 直接使用為本 feature 的 index |

無需轉換層；002 的 Parquet 直接 `pd.read_parquet()` 即可餵入 `batch_compute`。

---

## 9. 不變式（Invariants）

實作 MUST 維護以下不變式，CI 測試應驗證：

1. **列數保留**：`len(batch_compute(df).output) == len(df)`（spec FR-001）。
2. **Index 保留**：輸出 index 與輸入完全相等（包含 dtype）。
3. **可重現性**：相同 `(df, params)` → byte-identical 輸出（spec FR-006）。
4. **批次 / 增量等價**：`batch(df).iloc[-1] == incremental(batch(df[:-1]).state, df.iloc[-1])`
   （spec FR-008）。
5. **參數不變**：`SMCFeatureParams` 與 `SMCEngineState` 為 frozen，不允許就地修改。
6. **NaN 列不污染下游**：對 `quality_flag != "ok"` 列，內部狀態（swing buffer、ATR buffer）
   MUST 跳過該列，不納入計算（spec FR-015）。
7. **CHoCh 優先於 BOS**：同根 K 棒同時觸發時，`bos_signal == 0 AND choch_signal != 0`
   （spec FR-019）。
