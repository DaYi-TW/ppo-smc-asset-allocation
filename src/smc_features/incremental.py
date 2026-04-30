"""``incremental_compute`` — 在 ``SMCEngineState`` 上推進一根新 K 棒。

策略（research R6）
-------------------

``SMCEngineState.window_bars`` 在 ``batch_compute`` 完成後保留**完整歷史**
OHLCV（spec FR-008 / invariant 4 byte-identical 的硬性要求 — swing/FVG/OB
偵測為跨段累積，視窗截斷會破壞等價性）。``incremental_compute`` 接到
``new_bar`` 後：

1. 驗證 timestamp 嚴格大於視窗最後一根。
2. 驗證 OHLCV 欄位齊備。
3. 將完整視窗 + new_bar 合併為 DataFrame，呼叫 ``batch_compute`` 計算，
   從中取出**新根**的 ``FeatureRow``。
4. 回傳新的 ``SMCEngineState``（其 window_bars 含 new_bar，可串接後續 incremental 呼叫）。

如此 batch / incremental 自動 byte-identical：兩條路徑走同一份 ``batch_compute``
程式碼，差別只在輸入長度。

複雜度：每次 ``incremental_compute`` 為 O(N)，N = bar_count。日線 N ≤ 5000，
單次 < 10 ms（spec SC-003）— 與全 batch 重算約等。對 PPO 訓練/推論的單根
推進場景來說，此 trade-off 換來 byte-identical 等價，遠勝近似快速版。
"""

from __future__ import annotations

import pandas as pd

from smc_features.batch import batch_compute
from smc_features.types import (
    FeatureRow,
    SMCEngineState,
)

_REQUIRED_FIELDS = ("open", "high", "low", "close", "volume")


def incremental_compute(
    prior_state: SMCEngineState,
    new_bar: pd.Series,
) -> tuple[FeatureRow, SMCEngineState]:
    """推進引擎一根 K 棒，回傳新列特徵與更新後 state。

    Args:
        prior_state: 先前 ``batch_compute`` 或 ``incremental_compute`` 的輸出
            state；必含 ``window_bars`` 視窗（完整歷史）。
        new_bar: 名稱為新 K 棒 ``pd.Timestamp`` 的 Series；至少含
            ``open / high / low / close / volume``，可選 ``quality_flag``。

    Returns:
        ``(FeatureRow, SMCEngineState)``。

    Raises:
        ValueError: ``new_bar.name`` 非 timestamp 或 ≤ 上一根 timestamp，或
            ``prior_state`` 為初始狀態（``bar_count == 0``，沒有歷史可拼接）。
        KeyError: 缺必要欄位。

    Example:
        >>> import pandas as pd
        >>> from smc_features import (
        ...     SMCFeatureParams, batch_compute, incremental_compute,
        ... )
        >>> idx = pd.date_range("2024-01-01", periods=20, freq="D")
        >>> df = pd.DataFrame({
        ...     "open": [100.0 + i * 0.5 for i in range(20)],
        ...     "high": [101.0 + i * 0.5 for i in range(20)],
        ...     "low": [99.0 + i * 0.5 for i in range(20)],
        ...     "close": [100.2 + i * 0.5 for i in range(20)],
        ...     "volume": [1_000_000] * 20,
        ... }, index=idx)
        >>> state = batch_compute(df, SMCFeatureParams()).state
        >>> new_bar = pd.Series(
        ...     {"open": 110.0, "high": 111.0, "low": 109.0,
        ...      "close": 110.5, "volume": 999_000},
        ...     name=idx[-1] + pd.Timedelta(days=1),
        ... )
        >>> row, new_state = incremental_compute(state, new_bar)
        >>> new_state.bar_count == state.bar_count + 1
        True
        >>> row.timestamp == idx[-1] + pd.Timedelta(days=1)
        True
    """
    # (a) 驗證 new_bar timestamp。
    if not isinstance(new_bar.name, pd.Timestamp):
        raise ValueError(
            f"new_bar.name 必須為 pd.Timestamp，收到 {type(new_bar.name)}"
        )
    new_ts: pd.Timestamp = new_bar.name
    if not prior_state.window_bars:
        raise ValueError(
            "prior_state.window_bars 為空；incremental_compute 需要 batch_compute 的 terminal state"
        )
    last_ts_ns = prior_state.window_bars[-1][0]
    last_ts = pd.Timestamp(last_ts_ns, unit="ns")
    if new_ts <= last_ts:
        raise ValueError(
            f"new_bar timestamp {new_ts} 必須嚴格晚於上一根 {last_ts}"
        )

    # (b) 驗證欄位齊備。
    missing = [c for c in _REQUIRED_FIELDS if c not in new_bar.index]
    if missing:
        raise KeyError(f"new_bar 缺必要欄位：{missing}")

    # (c) 構造完整 DataFrame：prior window_bars + new_bar。
    cols = ["open", "high", "low", "close", "volume"]
    rows: list[list[float]] = []
    qfs: list[str] = []
    index: list[pd.Timestamp] = []
    for ts_ns, o, h, l_, c, v, valid in prior_state.window_bars:
        index.append(pd.Timestamp(ts_ns, unit="ns"))
        rows.append([o, h, l_, c, v])
        qfs.append("ok" if valid else "missing_close")

    new_qf = "ok"
    if "quality_flag" in new_bar.index:
        qf_val = new_bar["quality_flag"]
        if isinstance(qf_val, str):
            new_qf = qf_val
    index.append(new_ts)
    rows.append(
        [
            float(new_bar["open"]),
            float(new_bar["high"]),
            float(new_bar["low"]),
            float(new_bar["close"]),
            float(new_bar["volume"]),
        ]
    )
    qfs.append(new_qf)

    df = pd.DataFrame(
        rows,
        index=pd.DatetimeIndex(index),
        columns=cols,
    )
    df["quality_flag"] = qfs

    # (d) 跑批次計算（include_aux=True 以填充 row aux 欄位）。
    br = batch_compute(df, prior_state.params, include_aux=True)
    last_row = br.output.iloc[-1]

    def _i(name: str) -> int:
        v = last_row[name]
        if pd.isna(v):
            return 0
        return int(v)

    def _f(name: str) -> float:
        v = last_row[name]
        if pd.isna(v):
            return float("nan")
        return float(v)

    def _b(name: str) -> bool:
        v = last_row[name]
        if pd.isna(v):
            return False
        return bool(v)

    def _bool_aux(name: str) -> bool | None:
        v = last_row[name]
        if pd.isna(v):
            return None
        return bool(v)

    def _float_aux(name: str) -> float | None:
        v = last_row[name]
        if pd.isna(v):
            return None
        return float(v)

    feature_row = FeatureRow(
        timestamp=new_ts,
        bos_signal=_i("bos_signal"),
        choch_signal=_i("choch_signal"),
        fvg_distance_pct=_f("fvg_distance_pct"),
        ob_touched=_b("ob_touched"),
        ob_distance_ratio=_f("ob_distance_ratio"),
        swing_high_marker=_bool_aux("swing_high_marker"),
        swing_low_marker=_bool_aux("swing_low_marker"),
        fvg_top_active=_float_aux("fvg_top_active"),
        fvg_bottom_active=_float_aux("fvg_bottom_active"),
        ob_top_active=_float_aux("ob_top_active"),
        ob_bottom_active=_float_aux("ob_bottom_active"),
    )

    return feature_row, br.state


__all__ = ["incremental_compute"]
