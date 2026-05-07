"""plotly 後端：產出互動式 HTML K 線圖（research R4）。

對應任務 T035：使用 plotly Candlestick 主圖，疊加 swing markers、FVG 矩形、
OB 矩形與 BOS / CHoCh 文字標註；輸出自包含 HTML（``include_plotlyjs="cdn"``）
以縮減檔案大小同時保證跨平台可離線開啟。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

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


def _add_band_shapes(
    fig: go.Figure,
    window: pd.DataFrame,
    top_col: str,
    bottom_col: str,
    color: str,
    opacity: float,
) -> None:
    top_arr = window[top_col].to_numpy(dtype=np.float64)
    bot_arr = window[bottom_col].to_numpy(dtype=np.float64)
    timestamps = window.index
    n = len(window)
    i = 0
    shapes: list[dict[str, Any]] = []
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
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "y",
                "x0": timestamps[start],
                "x1": timestamps[j - 1],
                "y0": cur_bot,
                "y1": cur_top,
                "fillcolor": color,
                "opacity": opacity,
                "line": {"width": 0},
                "layer": "below",
            }
        )
        i = j
    if shapes:
        existing = list(fig.layout.shapes) if fig.layout.shapes else []
        fig.update_layout(shapes=existing + shapes)


def _add_signal_annotations(fig: go.Figure, window: pd.DataFrame) -> None:
    bos = window["bos_signal"].to_numpy()
    choch = window["choch_signal"].to_numpy()
    highs = window["high"].to_numpy(dtype=np.float64)
    lows = window["low"].to_numpy(dtype=np.float64)
    timestamps = window.index
    annotations: list[dict[str, Any]] = []
    for i in range(len(window)):
        ch_val = choch[i] if not pd.isna(choch[i]) else 0
        bs_val = bos[i] if not pd.isna(bos[i]) else 0
        if ch_val == 1:
            annotations.append(
                {
                    "x": timestamps[i],
                    "y": highs[i] * 1.01,
                    "text": "CHoCh↑",
                    "showarrow": False,
                    "font": {"size": 10, "color": "#9467bd"},
                }
            )
        elif ch_val == -1:
            annotations.append(
                {
                    "x": timestamps[i],
                    "y": lows[i] * 0.99,
                    "text": "CHoCh↓",
                    "showarrow": False,
                    "font": {"size": 10, "color": "#9467bd"},
                }
            )
        elif bs_val == 1:
            annotations.append(
                {
                    "x": timestamps[i],
                    "y": highs[i] * 1.005,
                    "text": "BOS↑",
                    "showarrow": False,
                    "font": {"size": 10, "color": "#1f77b4"},
                }
            )
        elif bs_val == -1:
            annotations.append(
                {
                    "x": timestamps[i],
                    "y": lows[i] * 0.995,
                    "text": "BOS↓",
                    "showarrow": False,
                    "font": {"size": 10, "color": "#1f77b4"},
                }
            )
    if annotations:
        existing = list(fig.layout.annotations) if fig.layout.annotations else []
        fig.update_layout(annotations=existing + annotations)


def _add_swing_markers(fig: go.Figure, window: pd.DataFrame) -> None:
    sh_mask = window["swing_high_marker"].fillna(False).to_numpy(dtype=bool)
    sl_mask = window["swing_low_marker"].fillna(False).to_numpy(dtype=bool)
    if sh_mask.any():
        sh_x = window.index[sh_mask]
        sh_y = window["high"].to_numpy(dtype=np.float64)[sh_mask] * 1.002
        fig.add_trace(
            go.Scatter(
                x=sh_x,
                y=sh_y,
                mode="markers",
                marker={"symbol": "triangle-down", "color": "#d62728", "size": 9},
                name="Swing High",
            )
        )
    if sl_mask.any():
        sl_x = window.index[sl_mask]
        sl_y = window["low"].to_numpy(dtype=np.float64)[sl_mask] * 0.998
        fig.add_trace(
            go.Scatter(
                x=sl_x,
                y=sl_y,
                mode="markers",
                marker={"symbol": "triangle-up", "color": "#2ca02c", "size": 9},
                name="Swing Low",
            )
        )


def render_html(
    df_with_features: pd.DataFrame,
    time_range: tuple[pd.Timestamp, pd.Timestamp],
    output_path: Path | str,
    params: SMCFeatureParams | None = None,
) -> None:
    """產出互動式 HTML K 線圖（含 SMC overlays）。

    Args:
        df_with_features: ``batch_compute(..., include_aux=True)`` 的輸出。
        time_range: ``(start, end)`` 含括端點，必須在 ``df.index`` 內。
        output_path: HTML 檔案路徑；父目錄必須存在。
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

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=window.index,
                open=window["open"],
                high=window["high"],
                low=window["low"],
                close=window["close"],
                name="OHLC",
            )
        ]
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=620,
        margin={"l": 50, "r": 30, "t": 50, "b": 80},
    )
    _add_band_shapes(fig, window, "fvg_top_active", "fvg_bottom_active", "#1f77b4", 0.18)
    _add_band_shapes(fig, window, "ob_top_active", "ob_bottom_active", "#ff7f0e", 0.22)
    _add_swing_markers(fig, window)
    _add_signal_annotations(fig, window)

    if params is not None:
        footnote = (
            f"swing_length={params.swing_length}  "
            f"fvg_min_pct={params.fvg_min_pct}  "
            f"ob_lookback_bars={params.ob_lookback_bars}  "
            f"atr_window={params.atr_window}"
        )
        existing = list(fig.layout.annotations) if fig.layout.annotations else []
        existing.append(
            {
                "x": 0.5,
                "y": -0.12,
                "xref": "paper",
                "yref": "paper",
                "text": footnote,
                "showarrow": False,
                "font": {"size": 10, "color": "#555555"},
            }
        )
        fig.update_layout(annotations=existing)

    fig.write_html(
        output_path,
        include_plotlyjs="cdn",
        full_html=True,
        auto_open=False,
    )


__all__ = ["render_html"]
