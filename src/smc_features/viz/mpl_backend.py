"""mplfinance 後端：產出靜態 PNG K 線圖（research R4）。

對應任務 T034：在 K 棒圖上疊加 swing 標記、FVG 矩形帶、OB 矩形帶與
BOS/CHoCh 文字標籤；當 ``params`` 不為 ``None`` 時於圖底加入參數 footnote
（spec FR-011）。

設計選擇
--------

* 靜態圖選 mplfinance 而非 matplotlib 直畫，因為 mplfinance 的
  ``addplot`` 與 fig 控制 API 已內建 OHLC 對齊，可降低跨平台像素差異
  的風險（雖然像素級 byte-identical 並非本後端目標 — spec SC-002 僅針對
  特徵數值）。
* 以 ``Agg`` 後端強制 headless；CI 與容器無 GUI 也能輸出。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib

matplotlib.use("Agg")  # 強制 headless 後端；必須在 pyplot import 前設定。

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from smc_features.types import SMCFeatureParams


_REQUIRED_AUX_COLUMNS = (
    "swing_high_marker",
    "swing_low_marker",
    "fvg_top_active",
    "fvg_bottom_active",
    "ob_top_active",
    "ob_bottom_active",
)
_REQUIRED_FEATURE_COLUMNS = (
    "bos_signal",
    "choch_signal",
)


def _slice_window(
    df: pd.DataFrame,
    time_range: tuple[pd.Timestamp, pd.Timestamp],
) -> pd.DataFrame:
    start, end = time_range
    if start > end:
        raise ValueError(f"time_range 起點晚於終點：{start} > {end}")
    if start < df.index[0] or end > df.index[-1]:
        raise ValueError(f"time_range {start}~{end} 超出 index 範圍 {df.index[0]}~{df.index[-1]}")
    return df.loc[start:end].copy()


def _validate_columns(df: pd.DataFrame) -> None:
    missing_aux = [c for c in _REQUIRED_AUX_COLUMNS if c not in df.columns]
    if missing_aux:
        raise ValueError(
            f"缺少 aux 欄位 {missing_aux}；請以 batch_compute(..., include_aux=True) 產出。"
        )
    missing_feat = [c for c in _REQUIRED_FEATURE_COLUMNS if c not in df.columns]
    if missing_feat:
        raise KeyError(f"缺少特徵欄位 {missing_feat}；df_with_features 必須來自 batch_compute。")


def _build_swing_addplots(window: pd.DataFrame) -> list[Any]:
    addplots: list[Any] = []
    swing_high_y = np.where(
        window["swing_high_marker"].fillna(False).to_numpy(dtype=bool),
        window["high"].to_numpy(dtype=np.float64) * 1.002,
        np.nan,
    )
    swing_low_y = np.where(
        window["swing_low_marker"].fillna(False).to_numpy(dtype=bool),
        window["low"].to_numpy(dtype=np.float64) * 0.998,
        np.nan,
    )
    if not np.isnan(swing_high_y).all():
        addplots.append(
            mpf.make_addplot(
                swing_high_y,
                type="scatter",
                marker="v",
                markersize=60,
                color="#d62728",
            )
        )
    if not np.isnan(swing_low_y).all():
        addplots.append(
            mpf.make_addplot(
                swing_low_y,
                type="scatter",
                marker="^",
                markersize=60,
                color="#2ca02c",
            )
        )
    return addplots


def _draw_band(
    ax: Any,
    window: pd.DataFrame,
    top_col: str,
    bottom_col: str,
    color: str,
    alpha: float,
) -> None:
    """以橫向矩形描繪連續成立的 FVG 或 OB 帶。

    將 ``top_col`` / ``bottom_col`` 中連續非 NaN 段切成一個矩形；段切換或值
    變動時換成新矩形，避免不同 FVG / OB 被誤連成一塊。
    """
    top_arr = window[top_col].to_numpy(dtype=np.float64)
    bot_arr = window[bottom_col].to_numpy(dtype=np.float64)
    n = len(window)
    i = 0
    while i < n:
        if np.isnan(top_arr[i]) or np.isnan(bot_arr[i]):
            i += 1
            continue
        cur_top = top_arr[i]
        cur_bot = bot_arr[i]
        start = i
        j = i + 1
        while (
            j < n
            and not np.isnan(top_arr[j])
            and not np.isnan(bot_arr[j])
            and top_arr[j] == cur_top
            and bot_arr[j] == cur_bot
        ):
            j += 1
        rect = mpatches.Rectangle(
            (start - 0.4, cur_bot),
            (j - 1) - start + 0.8,
            cur_top - cur_bot,
            facecolor=color,
            alpha=alpha,
            edgecolor=color,
            linewidth=0.5,
        )
        ax.add_patch(rect)
        i = j


def _annotate_signals(ax: Any, window: pd.DataFrame) -> None:
    bos = window["bos_signal"].to_numpy()
    choch = window["choch_signal"].to_numpy()
    highs = window["high"].to_numpy(dtype=np.float64)
    lows = window["low"].to_numpy(dtype=np.float64)
    for i in range(len(window)):
        ch_val = choch[i] if not pd.isna(choch[i]) else 0
        bs_val = bos[i] if not pd.isna(bos[i]) else 0
        if ch_val == 1:
            ax.annotate(
                "CHoCh↑",
                xy=(i, highs[i]),
                xytext=(i, highs[i] * 1.01),
                fontsize=7,
                color="#9467bd",
                ha="center",
            )
        elif ch_val == -1:
            ax.annotate(
                "CHoCh↓",
                xy=(i, lows[i]),
                xytext=(i, lows[i] * 0.99),
                fontsize=7,
                color="#9467bd",
                ha="center",
            )
        elif bs_val == 1:
            ax.annotate(
                "BOS↑",
                xy=(i, highs[i]),
                xytext=(i, highs[i] * 1.005),
                fontsize=7,
                color="#1f77b4",
                ha="center",
            )
        elif bs_val == -1:
            ax.annotate(
                "BOS↓",
                xy=(i, lows[i]),
                xytext=(i, lows[i] * 0.995),
                fontsize=7,
                color="#1f77b4",
                ha="center",
            )


def render_png(
    df_with_features: pd.DataFrame,
    time_range: tuple[pd.Timestamp, pd.Timestamp],
    output_path: Path | str,
    params: SMCFeatureParams | None = None,
) -> None:
    """產出 PNG K 線圖（含 SMC overlays）。

    Args:
        df_with_features: ``batch_compute(..., include_aux=True)`` 的輸出。
        time_range: ``(start, end)`` 含括端點，必須在 ``df.index`` 內。
        output_path: PNG 檔案路徑；父目錄必須存在。
        params: 若提供，在圖底加入參數 footnote（FR-011）。

    Raises:
        ValueError: ``time_range`` 越界、aux 欄位缺失、或父目錄不存在。
        KeyError: 特徵欄位缺失。
    """
    _validate_columns(df_with_features)
    output_path = Path(output_path)
    if not output_path.parent.exists():
        raise ValueError(f"輸出父目錄不存在：{output_path.parent}")

    window = _slice_window(df_with_features, time_range)
    if window.empty:
        raise ValueError(f"time_range {time_range} 對應切片為空")

    addplots = _build_swing_addplots(window)
    fig, axes = mpf.plot(
        window[["open", "high", "low", "close", "volume"]],
        type="candle",
        style="yahoo",
        addplot=addplots if addplots else None,
        volume=True,
        returnfig=True,
        figsize=(12, 7),
        warn_too_much_data=10_000,
    )
    main_ax = axes[0]

    _draw_band(main_ax, window, "fvg_top_active", "fvg_bottom_active", "#1f77b4", 0.18)
    _draw_band(main_ax, window, "ob_top_active", "ob_bottom_active", "#ff7f0e", 0.22)
    _annotate_signals(main_ax, window)

    if params is not None:
        footnote = (
            f"swing_length={params.swing_length}  "
            f"fvg_min_pct={params.fvg_min_pct}  "
            f"ob_lookback_bars={params.ob_lookback_bars}  "
            f"atr_window={params.atr_window}"
        )
        fig.text(0.5, 0.01, footnote, ha="center", fontsize=8, color="#555555")

    try:
        fig.savefig(output_path, dpi=120, bbox_inches="tight")
    finally:
        with contextlib.suppress(Exception):
            plt.close(fig)


__all__ = ["render_png"]
