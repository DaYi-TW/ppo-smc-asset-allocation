"""``info`` dict 組裝與 JSON 序列化（data-model §6、FR-026、SC-008）。

* :func:`build_info` — 組裝 17 個必填 key（contracts/info-schema.json）。
* :func:`info_to_json_safe` — 遞迴將 numpy 物件轉為 Python 原生型別，使
  ``json.dumps()`` 不會 raise；對 float64 round-trip 無精度損失。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np


def info_to_json_safe(info: dict[str, Any]) -> dict[str, Any]:
    """將 info dict 中所有 numpy 物件遞迴轉為 JSON 可序列化型別。

    轉換規則：

    * ``numpy.ndarray`` → ``list``（遞迴；``float32`` 會升為 Python ``float``，
      內部以 float64 表示，對 float64 round-trip 無損）。
    * ``numpy.float*`` → ``float``。
    * ``numpy.int*`` → ``int``。
    * ``numpy.bool_`` → ``bool``。
    * ``dict`` 與 ``list`` 遞迴下探。
    * 其他型別原樣回傳（依賴呼叫端確保已合法）。
    """
    return _convert(info)


def _convert(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {k: _convert(v) for k, v in value.items()}
    if isinstance(value, Mapping):
        return {k: _convert(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_convert(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_convert(v) for v in value.tolist()]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def build_info(
    *,
    date_str: str,
    weights: np.ndarray,
    nav: float,
    peak_nav: float,
    asset_values: np.ndarray,
    cash: float,
    turnover: float,
    slippage_bps: float,
    log_return: float,
    drawdown_penalty: float,
    turnover_penalty: float,
    action_raw: np.ndarray,
    action_processed: np.ndarray,
    action_renormalized: bool,
    position_capped: bool,
    nan_replaced: int,
    is_initial_step: bool,
    data_hashes: Mapping[str, str],
    skipped_dates: list[str],
) -> dict[str, Any]:
    """組裝 17 個必填 key 之 info dict。

    ``reward_components`` 為巢狀 dict，鍵順序固定為 ``log_return →
    drawdown_penalty → turnover_penalty``，便於 JSON Schema 驗證與 log 可讀性。
    所有數值已轉為 Python ``float`` / ``bool`` / ``int``（避免 numpy scalar 殘留
    於外層 dict 造成下游 JSON 序列化額外開銷）。
    """
    return {
        "date": date_str,
        "weights": [float(w) for w in weights],
        "nav": float(nav),
        "peak_nav": float(peak_nav),
        "cash": float(cash),
        "asset_values": [float(v) for v in asset_values],
        "turnover": float(turnover),
        "slippage_bps": float(slippage_bps),
        "reward_components": {
            "log_return": float(log_return),
            "drawdown_penalty": float(drawdown_penalty),
            "turnover_penalty": float(turnover_penalty),
        },
        "action_raw": [float(v) for v in action_raw],
        "action_processed": [float(v) for v in action_processed],
        "action_renormalized": bool(action_renormalized),
        "position_capped": bool(position_capped),
        "nan_replaced": int(nan_replaced),
        "is_initial_step": bool(is_initial_step),
        "data_hashes": data_hashes,
        "skipped_dates": list(skipped_dates),
    }


__all__ = ["build_info", "info_to_json_safe"]
