# Contract: `incremental` ↔ `batch_compute` 等價性

**Module**: `src/smc_features/incremental.py`
**Functions**: `init_state(...)`, `step(state, bar) -> StepResult`
**Version**: v2 (feature 008)

## Equivalence claim

對任意 OHLCV 序列（時間長度 n、含合理 valid_mask 模式），下列兩種計算方式 MUST 產出**相同的事件序列與最終 state**：

```python
# Path A: batch
result_a = batch_compute(timestamps, opens, highs, lows, closes, valid_mask, params)

# Path B: incremental
state = init_state(params)
all_breaks = []
for i in range(n):
    step_result = step(state, Bar(timestamps[i], opens[i], highs[i], lows[i], closes[i], valid_mask[i]))
    all_breaks.extend(step_result.new_breaks)

# 等價性
assert all_breaks == list(result_a.breaks)
```

## Invariants（contract test 驗收）

### Invariant I-1：breaks 列表完全相同

```python
batch_breaks = batch_result.breaks
inc_breaks = collected_from_incremental
assert len(batch_breaks) == len(inc_breaks)
for a, b in zip(batch_breaks, inc_breaks):
    assert a.kind == b.kind
    assert a.time == b.time
    assert a.bar_index == b.bar_index
    assert a.break_price == b.break_price
    assert a.anchor_swing_bar_index == b.anchor_swing_bar_index
    assert a.anchor_swing_price == b.anchor_swing_price
    assert a.trend_after == b.trend_after
```

### Invariant I-2：signal array 完全相同

`incremental.step` 累積出的 `bos_signal_inc`、`choch_signal_inc`（每根 K 一個 int8）必須與 `batch_result.bos_signal`、`batch_result.choch_signal` 全等。

### Invariant I-3：OB 列表（含 source_break_*）完全相同

兩路徑產出的 `obs` 列表長度、順序、每個欄位皆相同。`source_break_index` 因兩路徑的 breaks 列表相同（I-1）而自然對齊。

### Invariant I-4：FVG 列表完全相同

包含 ATR 過濾後的留存與否判定。

### Invariant I-5：State 一致性

incremental 跑完 n 根 K 後，state 的下列關鍵欄位必須與 batch 在第 n-1 根「概念上的對應 state」一致：

- `last_swing_high`、`last_swing_low`（位置與價位）
- `trend`
- `used_swing_high_bar_indices`、`used_swing_low_bar_indices`（dedup 集合）
- `active_obs`（未失效 OB 列表）

註：`atr_state` 等內部 streaming 狀態不在比對範圍——僅比對「外部可觀察」的事件結果。

## 測試方案

### 隨機等價測試（contract test）

```python
@pytest.mark.parametrize("seed", [0, 1, 2, 42, 1337])
def test_batch_incremental_equivalence(seed):
    rng = np.random.default_rng(seed)
    n = 1000
    # 生成隨機 random walk OHLCV
    closes = 100 + np.cumsum(rng.standard_normal(n))
    opens = closes + rng.standard_normal(n) * 0.1
    highs = np.maximum(opens, closes) + np.abs(rng.standard_normal(n)) * 0.5
    lows = np.minimum(opens, closes) - np.abs(rng.standard_normal(n)) * 0.5
    timestamps = np.arange("2024-01-01", n, dtype="datetime64[D]")
    valid_mask = np.ones(n, dtype=np.bool_)
    params = SMCFeatureParams()

    batch_result = batch_compute(timestamps, opens, highs, lows, closes, valid_mask, params)

    state = init_state(params)
    inc_breaks = []
    for i in range(n):
        sr = step(state, Bar(timestamps[i], opens[i], highs[i], lows[i], closes[i], valid_mask[i]))
        inc_breaks.extend(sr.new_breaks)

    assert inc_breaks == list(batch_result.breaks)
    # 進一步：signal array、obs、fvgs 比對
```

### 邊界 case 測試

| Case | 期待 |
|---|---|
| n=0 空序列 | 兩路徑皆無錯，breaks=[] |
| 全部 valid_mask=False | breaks=[] |
| n=1 單根 K | breaks=[]（無 swing 可形成） |
| 序列前 swing_length 根 | swing marker 為 False，無 break event |

## 實作提示

incremental step 函式應分離「規則邏輯」與「state 推進」兩個責任——讓 batch.py 可內部呼叫 step 來保證等價。建議架構：

```python
def step(state: IncrementalState, bar: Bar) -> StepResult:
    # 1. 檢查 break event（吃 state 中的 last_swing_* 與 used_*）
    new_breaks = _detect_breaks(state, bar)
    # 2. 更新 trend
    state.trend = _update_trend(state.trend, new_breaks)
    # 3. 處理本根 K 是否被確認為新 swing（可能被 detect_swings 提前計算）
    _maybe_update_swings(state, bar)
    # 4. OB 失效判定 + 新 break 觸發 OB 偵測
    _process_obs(state, bar, new_breaks)
    # 5. FVG 偵測（含 ATR 過濾）
    _process_fvgs(state, bar)
    # 6. ATR 增量更新
    _update_atr(state, bar)
    return StepResult(new_breaks=new_breaks, ...)
```

batch.py 改寫為「準備所有依賴（如 swing markers）後逐根呼叫 step」可一勞永逸保證等價。但這是 implementation 階段的選擇，不在 contract 強制範圍。
