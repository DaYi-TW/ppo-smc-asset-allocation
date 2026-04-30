"""SMC 特徵視覺化雙後端（spec FR-009~FR-011 / research R4）。

* ``visualize(..., fmt="png")``：mplfinance 後端，輸出靜態 PNG。
* ``visualize(..., fmt="html")``：plotly 後端，輸出互動式 HTML。

dispatcher 在此檔；後端實作分別位於 ``mpl_backend.py`` 與 ``plotly_backend.py``，
保持 import 延遲（只在實際呼叫時匯入），讓 headless / 不裝 viz 套件的部署
（例如 PPO 服務）只需匯入核心仍可運作。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from smc_features.types import SMCFeatureParams


def visualize(
    df_with_features: pd.DataFrame,
    time_range: tuple[pd.Timestamp, pd.Timestamp],
    output_path: Path | str,
    fmt: Literal["png", "html"] = "png",
    *,
    params: SMCFeatureParams | None = None,
) -> None:
    """產出附帶 SMC overlays 的 K 線圖（spec FR-009~FR-011）。

    Args:
        df_with_features: ``batch_compute(..., include_aux=True)`` 的輸出；
            必須含 6 個 aux 欄位與 bos/choch 特徵欄位。
        time_range: ``(start, end)`` 含括端點，必須落在 ``df.index`` 內。
        output_path: 輸出檔案路徑；父目錄必須存在。
        fmt: ``"png"`` 走 mplfinance；``"html"`` 走 plotly。
        params: 若提供，在圖底加入參數 footnote（FR-011）；``None`` 則不繪。

    Raises:
        ValueError: ``time_range`` 越界、aux 欄位缺失、父目錄不存在、或 ``fmt``
            非允許值。
        KeyError: 特徵欄位缺失。
    """
    if fmt == "png":
        from smc_features.viz.mpl_backend import render_png

        render_png(df_with_features, time_range, output_path, params)
        return
    if fmt == "html":
        from smc_features.viz.plotly_backend import render_html

        render_html(df_with_features, time_range, output_path, params)
        return
    raise ValueError(f"fmt 必須為 'png' 或 'html'，收到 {fmt!r}")


__all__ = ["visualize"]
