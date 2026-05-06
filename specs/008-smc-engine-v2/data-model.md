# Data Model: SMC Engine v2

**Feature**: 008-smc-engine-v2
**Phase**: 1 — Design

定義 v2 引入或修改的資料型別。所有 dataclass 採 `frozen=True`、`slots=True`，欄位 JSON-serializable（為 Constitution Gate IV-2）。

---

## 1. `StructureBreak`（新增）

代表一個 BOS 或 CHoCh 事件。

```python
from dataclasses import dataclass
from typing import Literal
import numpy as np

BreakKind = Literal["BOS_BULL", "BOS_BEAR", "CHOCH_BULL", "CHOCH_BEAR"]
TrendState = Literal["bullish", "bearish", "neutral"]

@dataclass(frozen=True, slots=True)
class StructureBreak:
    kind: BreakKind                 # 事件類型
    time: np.datetime64             # 突破當下 K 棒時間戳（與 OHLCV.timestamps 同 dtype）
    bar_index: int                  # 突破當下 K 棒在序列中的位置
    break_price: float              # 突破當下 close
    anchor_swing_time: np.datetime64
    anchor_swing_bar_index: int
    anchor_swing_price: float       # 被突破的 swing high/low 價位
    trend_after: TrendState         # 事件處理完之後的 trend
```

### 約束

- `bar_index >= anchor_swing_bar_index + 1`（突破必須晚於 anchor swing 的形成）。
- `kind == "BOS_BULL"` ⇒ `break_price > anchor_swing_price` 且 `trend_after == "bullish"`。
- `kind == "CHOCH_BULL"` ⇒ `break_price > anchor_swing_price` 且 `trend_after == "bullish"`。
- `kind == "BOS_BEAR"` ⇒ `break_price < anchor_swing_price` 且 `trend_after == "bearish"`。
- `kind == "CHOCH_BEAR"` ⇒ `break_price < anchor_swing_price` 且 `trend_after == "bearish"`。
- 「初始 BOS」（neutral → bullish/bearish）算 BOS_*（不算 CHoCh），`anchor_swing_*` 必須對應序列中真實存在的 swing point（不可為 None）。

### 等價於 signal array 的對應

`bos_signal[break.bar_index] = ±1` ⇔ `break.kind in {BOS_BULL, BOS_BEAR}`
`choch_signal[break.bar_index] = ±1` ⇔ `break.kind in {CHOCH_BULL, CHOCH_BEAR}`

每個非零位置對應 `breaks` 列表中**恰好一個** event。反向亦然——這是 contract test 的可驗證項。

---

## 2. `OrderBlock`（v2 — 擴充欄位）

```python
@dataclass(frozen=True, slots=True)
class OrderBlock:
    # === v1 既有欄位（保留） ===
    formation_timestamp: np.datetime64
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float
    bottom: float
    midpoint: float
    expiry_bar_index: int
    invalidated: bool
    invalidation_timestamp: np.datetime64 | None

    # === v2 新增欄位 ===
    source_break_index: int                 # 在 BatchResult.breaks 列表中的索引
    source_break_kind: BreakKind            # 觸發此 OB 的 break 種類（冗餘但便於前端 hover）
```

### 約束

- `formation_bar_index < source_break.bar_index`（OB 必形成於 break 之前）。
- bullish OB ⇒ `source_break_kind in {BOS_BULL, CHOCH_BULL}`。
- bearish OB ⇒ `source_break_kind in {BOS_BEAR, CHOCH_BEAR}`。
- `top > bottom`（嚴格）；`midpoint = (top + bottom) / 2`。
- 失效規則沿用 v1（時間 + 結構），失效後 `invalidated = True` 且 `invalidation_timestamp` 設定。

---

## 3. `FairValueGap`（v2 — 不改 schema，僅改偵測流程）

欄位完全沿用 v1：

```python
@dataclass(frozen=True, slots=True)
class FairValueGap:
    formation_timestamp: np.datetime64
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float
    bottom: float
    is_filled: bool
    fill_timestamp: np.datetime64 | None
    fill_bar_index: int | None
```

**v2 行為差異**（不改 schema）：
- 偵測時加入 ATR 過濾（見 Decision 3）；通過過濾的 FVG 才會被加入列表。
- 結果：列表變短，但欄位結構完全不變——下游（fixture builder、`fvg_distance_pct` 計算）不需要任何 schema migration。

---

## 4. `SMCFeatureParams`（v2 — 新增欄位）

```python
@dataclass(frozen=True, slots=True)
class SMCFeatureParams:
    # === v1 既有欄位（保留預設值） ===
    swing_length: int = 5
    fvg_min_pct: float = 0.001
    ob_lookback_bars: int = 50
    atr_window: int = 14

    # === v2 新增欄位 ===
    fvg_min_atr_ratio: float = 0.25         # 0.0 = 退化為僅 fvg_min_pct（v1 行為）
```

### 向後相容

- `fvg_min_atr_ratio` 用 `default=0.25` 後置加入，現有所有位置呼叫（如 feature 002 / fixture builder）不受影響。
- 設為 `0.0` 等價於關閉 ATR 過濾（v1 行為），便於 ablation 對比。

---

## 5. `BatchResult`（v2 — 新增欄位）

```python
@dataclass(frozen=True, slots=True)
class BatchResult:
    # === v1 既有欄位（保留） ===
    swing_high_marker: NDArray[np.bool_]
    swing_low_marker: NDArray[np.bool_]
    bos_signal: NDArray[np.int8]
    choch_signal: NDArray[np.int8]
    fvgs: list[FairValueGap]
    obs: list[OrderBlock]
    ob_touched: NDArray[np.bool_]
    ob_distance_ratio: NDArray[np.float64]
    fvg_distance_pct: NDArray[np.float64]
    atr: NDArray[np.float64]

    # === v2 新增欄位 ===
    breaks: list[StructureBreak]            # 與 bos_signal/choch_signal 一致的事件列表
```

### 約束（contract test 驗收）

對任意 `BatchResult` 實例：

```
sum(abs(bos_signal)) + sum(abs(choch_signal)) == len(breaks)
```

且：

```
for b in breaks:
    if b.kind.startswith("BOS"):
        assert bos_signal[b.bar_index] == (+1 if "BULL" in b.kind else -1)
        assert choch_signal[b.bar_index] == 0
    else:
        assert choch_signal[b.bar_index] == (+1 if "BULL" in b.kind else -1)
        assert bos_signal[b.bar_index] == 0
```

---

## 6. `IncrementalState`（v2 — 新增 dedup state）

```python
@dataclass(slots=True)  # 注意：incremental state mutable，不 frozen
class IncrementalState:
    # === v1 既有欄位（保留） ===
    last_swing_high: SwingPoint | None
    prev_swing_high: SwingPoint | None
    last_swing_low: SwingPoint | None
    prev_swing_low: SwingPoint | None
    trend: TrendState
    atr_state: ATRState
    active_obs: list[OrderBlock]
    active_fvgs: list[FairValueGap]
    # ...

    # === v2 新增欄位 ===
    used_swing_high_bar_indices: set[int]   # FR-003 dedup 集合
    used_swing_low_bar_indices: set[int]
    pending_breaks: list[StructureBreak]    # 累積至呼叫者取走（FR-014）
```

### Dedup state 轉換規則

對某根 K 棒 `i`，valid_mask[i] = True：

```
1. 計算 candidate event：
   - if trend == bullish:
       - if last_swing_low not None and close[i] < last_swing_low.price
         and last_swing_low.bar_index not in used_swing_low_bar_indices:
           emit CHOCH_BEAR; used_swing_low_bar_indices.add(last_swing_low.bar_index); trend = bearish
       - elif last_swing_high not None and close[i] > last_swing_high.price
         and last_swing_high.bar_index not in used_swing_high_bar_indices:
           emit BOS_BULL; used_swing_high_bar_indices.add(last_swing_high.bar_index)
   - if trend == bearish: 對稱
   - if trend == neutral:
       - 第一次任一方向突破 → 視為初始 BOS_*（不發 CHoCh），設 trend，加 used

2. 若當根 K 同時被確認為 swing：
   - 先處理 break event（步驟 1）
   - 再更新 prev/last_swing_*
   - 注意：新形成的 swing 不在 used 集合內，下次可被突破
```

### Pending breaks 列出語意

`incremental.step(state, bar) -> StepResult`：每次呼叫，`StepResult.new_breaks: list[StructureBreak]` 含本根 K 新增的 events（通常 0 或 1 筆，理論上不會 ≥ 2 因 BOS/CHoCh 互斥）。呼叫者負責累積或消費；`state.pending_breaks` 不在 step 之間累積。

---

## 7. JSON 序列化規範（為 Gate IV-2）

`StructureBreak` 與 `OrderBlock` v2 必須能轉成 JSON：

| Python | JSON |
|---|---|
| `np.datetime64` | ISO 8601 string `"YYYY-MM-DDTHH:MM:SS"` |
| `int / float / bool / str` | 原樣 |
| `None` | `null` |
| `Literal[...]` | string |
| `list[X]` | array |

引擎本身**不**做 JSON 轉換（保持純 Python dataclass）。轉換責任在呼叫端（fixture builder、Spring gateway）。本 spec 只保證欄位皆 JSON-serializable，不直接提供 `to_json()` 方法。

---

## 8. 變更影響面

| 檔案 | 變更性質 |
|---|---|
| `src/smc_features/types.py` | 新增 `StructureBreak`、`BreakKind`、`TrendState`；擴 `OrderBlock`、`SMCFeatureParams`、`BatchResult`、`IncrementalState`、`StepResult` |
| `src/smc_features/__init__.py` | 對外 export `StructureBreak` |
| 上游消費者（feature 002、fixture builder、PPO env） | **零破壞**——所有 v1 欄位保留，v2 新欄位皆 optional / default 值；既有讀取邏輯無需修改 |

**Phase 1a 完成**。
