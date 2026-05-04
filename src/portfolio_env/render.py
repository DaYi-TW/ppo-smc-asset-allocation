"""Render（spec FR-027）— Gymnasium 0.29+ 慣例：``render_mode`` 於 __init__
固定，``render()`` 不接收 mode 參數。

支援兩種 mode：

* ``None`` — no-op，回傳 ``None``。
* ``"ansi"`` — 一行文字摘要（date / nav / peak / weights / reward 三項）。
"""

from __future__ import annotations

from typing import Any


def render_ansi(info: dict[str, Any], reward: float) -> str:
    """產出單行 ANSI 文字摘要。

    格式：``date={date} nav={nav:.4f} peak={peak:.4f} weights=[...] r={reward:+.6f}
    (log_ret={...}, dd_pen={...}, to_pen={...})``。
    """
    weights = info["weights"]
    weights_str = "[" + ",".join(f"{w:.3f}" for w in weights) + "]"
    rc = info["reward_components"]
    return (
        f"date={info['date']} "
        f"nav={info['nav']:.4f} "
        f"peak={info['peak_nav']:.4f} "
        f"weights={weights_str} "
        f"r={reward:+.6f} "
        f"(log_ret={rc['log_return']:+.6f}, "
        f"dd_pen={rc['drawdown_penalty']:.6f}, "
        f"to_pen={rc['turnover_penalty']:.6f})"
    )


__all__ = ["render_ansi"]
