# Contract: `incremental_compute` ↔ `batch_compute` 等價性

**Module**: `src/smc_features/incremental.py`
**Function**: `incremental_compute(prior_state: SMCEngineState, new_bar: pd.Series) -> tuple[FeatureRow, SMCEngineState]`
**Version**: v2 (feature 008)

## v2 對 v1 的差異

v1 的 `incremental_compute` 內部以 `batch_compute` 全重算尾段一根（research R6）。**v2 不改變此設計**——dedup state、break event 列表、ATR 過濾後 FVG 都已透過 `batch_compute` 回傳的 `BatchResult` 容器一次計算，incremental 重算的是同一份 batch 程式碼，等價性天然成立。

v2 改動範圍：

- `BatchResult` 多回 `breaks: tuple[StructureBreak, ...]`
- `FeatureRow.bos_signal` / `choch_signal` 為 dedup 後事件當下 ±1
- `FeatureRow.ob_touched` / `ob_distance_ratio` 由 break-driven OB 集合更新
- `FeatureRow.fvg_distance_pct` 取自 ATR 過濾後的 FVG 集合

`SMCEngineState` 維持 frozen，不新增 dedup state（dedup 在 `batch_compute` 內部以 local set 實現，因為 incremental 路徑透過全重算保持一致）。

## Equivalence claim

對任意 OHLCV 序列（時間長度 n、含合理 valid_mask 模式），下列兩種計算方式 MUST 產出**相同的最終 BatchResult.output 與 BatchResult.breaks**：

```python
# Path A: 一次 batch
result_a = batch_compute(df_full, params)

# Path B: 先 batch 前 n-1 根、再 incremental 推進最後一根
result_partial = batch_compute(df_full.iloc[:-1], params)
row_n, state_n = incremental_compute(result_partial.state, df_full.iloc[-1])

# 等價性
assert row_n == result_a.output.iloc[-1]  # FeatureRow 與 DataFrame 最後一列等值
# state_n 的 last_swing_*/trend_state/active_obs/open_fvgs 應與 result_a.state 一致
```

由於 `incremental_compute` 內部呼叫 `batch_compute(df_full, params)` 並取尾段一根，等價性是**結構性保證**，不依賴額外 state 比對；只要 `batch_compute` 是 deterministic、incremental 介面正確拼接 `prior_state.window_bars + new_bar`，等價即成立。

## Invariants（contract test 驗收）

### Invariant I-1：FeatureRow 等價

```python
batch_full = batch_compute(df, params)
batch_prefix = batch_compute(df.iloc[:-1], params)
row, _ = incremental_compute(batch_prefix.state, df.iloc[-1])
assert row.bos_signal == batch_full.output.iloc[-1]["bos_signal"]
assert row.choch_signal == batch_full.output.iloc[-1]["choch_signal"]
assert row.fvg_distance_pct == batch_full.output.iloc[-1]["fvg_distance_pct"]
assert row.ob_touched == batch_full.output.iloc[-1]["ob_touched"]
assert row.ob_distance_ratio == batch_full.output.iloc[-1]["ob_distance_ratio"]
```

### Invariant I-2：BatchResult.breaks 等價

```python
# 用同一 df 跑 batch_compute 兩次（一次 prefix + incremental 一根、一次 full），
# 比對 breaks 列表必須完全相同。
assert tuple(batch_full.breaks) == tuple(
    batch_compute(df_via_incremental_path, params).breaks
)
```

由於 v1 incremental 設計即「全重算」，I-2 在 v1 設計下天然成立；v2 不需新增 streaming-side 的 break 累積邏輯。

### Invariant I-3：State 一致性

incremental 推進完最後一根後，`SMCEngineState` 的下列關鍵欄位必須與一次跑 full batch 的 terminal state 一致：

- `last_swing_high`、`last_swing_low`（位置與價位）
- `prev_swing_high`、`prev_swing_low`
- `trend_state`
- `open_fvgs`（未填補 FVG）
- `active_obs`（未失效 OB）
- `bar_count`

`window_bars` / `atr_buffer` 等內部狀態不在比對範圍——比對「外部可觀察」的事件結果與快照結構。

## 測試方案

### Determinism / 等價性測試（contract test）

```python
@pytest.mark.parametrize("seed", [0, 1, 2, 42, 1337])
def test_batch_incremental_equivalence(make_random_ohlcv, seed):
    bundle = make_random_ohlcv(seed=seed, n=1000)
    df = pd.DataFrame(
        {
            "open": bundle["opens"],
            "high": bundle["highs"],
            "low": bundle["lows"],
            "close": bundle["closes"],
            "volume": [1_000_000] * 1000,
        },
        index=pd.DatetimeIndex(bundle["timestamps"]),
    )
    params = SMCFeatureParams()

    batch_full = batch_compute(df, params)
    batch_prefix = batch_compute(df.iloc[:-1], params)
    row, state_after = incremental_compute(batch_prefix.state, df.iloc[-1])

    last_row = batch_full.output.iloc[-1]
    assert row.bos_signal == last_row["bos_signal"]
    assert row.choch_signal == last_row["choch_signal"]
    # ... 其他欄位
    assert state_after.bar_count == batch_full.state.bar_count
    assert state_after.trend_state == batch_full.state.trend_state
```

### 邊界 case 測試

| Case | 期待 |
|---|---|
| n=0 空序列 | batch_compute 直接回 empty DataFrame、breaks=() |
| 全部 valid_mask=False | breaks=() |
| n=1 單根 K | breaks=()（無 swing 可形成） |
| 序列前 swing_length 根 | swing marker 為 False，無 break event |
| incremental 接 prior_state.bar_count==0 | ValueError（v1 既有行為，v2 沿用） |

## 實作提示

不要為 v2 新增 mutable streaming state 機制。dedup state 的正確實現位置是 `batch.py` 內部的單次 pass：

```python
def _compute_breaks_with_dedup(...):
    used_swing_high = set()
    used_swing_low = set()
    breaks = []
    for i in range(n):
        # ... 規則邏輯
    return breaks, bos_signal_array, choch_signal_array
```

這樣 incremental 透過全重算自動共享同一條 dedup pass，等價性天然成立、無須額外比對。
