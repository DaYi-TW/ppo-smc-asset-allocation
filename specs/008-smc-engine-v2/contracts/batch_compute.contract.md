# Contract: `batch_compute`

**Module**: `src/smc_features/batch.py`
**Function**: `batch_compute(...) -> BatchResult`
**Version**: v2 (feature 008)

## Signature

```python
def batch_compute(
    timestamps: NDArray[np.datetime64],
    opens: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    valid_mask: NDArray[np.bool_],
    params: SMCFeatureParams,
) -> BatchResult: ...
```

簽章與 v1 相同（`SMCFeatureParams` 雖新增欄位但 default 後置，呼叫端零修改）。

## Output schema（BatchResult v2）

| 欄位 | dtype / 型別 | shape | v1 v2 差異 |
|---|---|---|---|
| `swing_high_marker` | `bool_` | `(n,)` | 不變 |
| `swing_low_marker` | `bool_` | `(n,)` | 不變 |
| `bos_signal` | `int8` | `(n,)` | **dedup** — 同一 swing 突破期間僅事件當下=±1 |
| `choch_signal` | `int8` | `(n,)` | 同上 |
| `fvgs` | `list[FairValueGap]` | — | **數量減少** — ATR 過濾後密度下降 |
| `obs` | `list[OrderBlock]` | — | **數量減少 + schema 擴充** — break-driven，含 `source_break_*` |
| `ob_touched` | `bool_` | `(n,)` | 不變（語意：當前 K 與最近有效 OB 是否相交） |
| `ob_distance_ratio` | `float64` | `(n,)` | 不變（NaN 表無 active OB） |
| `fvg_distance_pct` | `float64` | `(n,)` | 不變 |
| `atr` | `float64` | `(n,)` | 不變 |
| **`breaks`** | `list[StructureBreak]` | — | **新增** |

## Invariants（contract test 驗收）

### Invariant B-1：bos/choch signal ↔ breaks 對應

```python
nonzero_bos_indices = np.flatnonzero(bos_signal)
nonzero_choch_indices = np.flatnonzero(choch_signal)
break_indices = sorted(b.bar_index for b in breaks)
assert sorted(list(nonzero_bos_indices) + list(nonzero_choch_indices)) == break_indices
```

### Invariant B-2：每個 break 對應 array 上恰一個非零

```python
for b in breaks:
    if b.kind.startswith("BOS"):
        expected = +1 if "BULL" in b.kind else -1
        assert bos_signal[b.bar_index] == expected
        assert choch_signal[b.bar_index] == 0
    else:
        expected = +1 if "BULL" in b.kind else -1
        assert choch_signal[b.bar_index] == expected
        assert bos_signal[b.bar_index] == 0
```

### Invariant B-3：OB ↔ break 對齊

```python
for ob in obs:
    assert 0 <= ob.source_break_index < len(breaks)
    src = breaks[ob.source_break_index]
    assert ob.source_break_kind == src.kind
    assert ob.formation_bar_index < src.bar_index
    if ob.direction == "bullish":
        assert src.kind in ("BOS_BULL", "CHOCH_BULL")
    else:
        assert src.kind in ("BOS_BEAR", "CHOCH_BEAR")
```

### Invariant B-4：dedup — 每個 anchor swing 最多被引用一次

```python
anchors = [(b.anchor_swing_bar_index, b.kind.endswith("BULL")) for b in breaks]
assert len(anchors) == len(set(anchors))  # 同一 swing + 方向只能出現一次
```

### Invariant B-5：FVG ATR 過濾正確

```python
for f in fvgs:
    height = f.top - f.bottom
    atr_at_formation = atr[f.formation_bar_index]
    if not np.isnan(atr_at_formation):
        assert height / atr_at_formation >= params.fvg_min_atr_ratio
    else:
        # warmup 期 ATR=NaN，退化為 fvg_min_pct 檢查
        mid = (f.top + f.bottom) / 2
        assert height / mid >= params.fvg_min_pct
```

### Invariant B-6：observation 介面相容

```python
# 模擬 PPO env 取觀測（不依賴 v2 新欄位）
obs_5ch = np.stack([
    bos_signal.astype(np.float32),
    choch_signal.astype(np.float32),
    fvg_distance_pct.astype(np.float32),
    ob_touched.astype(np.float32),
    ob_distance_ratio.astype(np.float32),
], axis=1)
assert obs_5ch.shape == (n, 5)
assert obs_5ch.dtype == np.float32
# 不能因為 v2 改造而出現 PPO env 期望外的 dtype 或 shape
```

### Invariant B-7：Determinism

對同一輸入 + 同一 `params`，呼叫兩次產出的 `BatchResult` 必須 byte-identical（含 `breaks` 列表中每個 dataclass 欄位、numpy array 全 `np.array_equal`）。

## 邊界條件

| 條件 | 期待行為 |
|---|---|
| 全部 K 棒 valid_mask=False | 所有 array 全 0 / NaN；`fvgs / obs / breaks` 皆 `[]` |
| 序列開頭尚無 swing | 該段 `bos_signal[i] = choch_signal[i] = 0`，無 break event |
| ATR warmup 期（i < atr_window） | FVG 走 `fvg_min_pct` 退化路徑；OB / break 偵測不受 ATR 影響 |
| 整段單邊行情（如連續上漲，無紅 K） | bullish breaks 仍可發生，但對應 OB 找不到反向 K → `len(obs) < len(bullish breaks)` |
| 同根 K 同時是 swing 又突破前 swing | 先發 break event 再更新 last_swing_*；該根 K 仍可被列入 swing marker |
