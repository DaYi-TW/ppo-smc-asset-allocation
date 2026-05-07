"""StructureBreak / OrderBlock v2 / SMCFeatureParams v2 dataclass 欄位完整性。

對應 spec FR-006 / FR-009 / FR-011、tasks.md T003。
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest


def test_structure_break_has_all_required_fields() -> None:
    """StructureBreak 應有 8 個必填欄位（spec FR-006、SC-005）。"""
    from smc_features.types import StructureBreak

    fields = {f.name for f in dataclasses.fields(StructureBreak)}
    expected = {
        "kind",
        "time",
        "bar_index",
        "break_price",
        "anchor_swing_time",
        "anchor_swing_bar_index",
        "anchor_swing_price",
        "trend_after",
    }
    assert fields == expected, f"欄位差異：{fields ^ expected}"


def test_structure_break_is_frozen() -> None:
    """StructureBreak 必須 frozen（Constitution I：Reproducibility）。"""
    from smc_features.types import StructureBreak

    sb = StructureBreak(
        kind="BOS_BULL",
        time=np.datetime64("2024-03-15T00:00:00"),
        bar_index=234,
        break_price=504.20,
        anchor_swing_time=np.datetime64("2024-02-28T00:00:00"),
        anchor_swing_bar_index=220,
        anchor_swing_price=487.50,
        trend_after="bullish",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        sb.kind = "BOS_BEAR"  # type: ignore[misc]


def test_structure_break_kind_literal_values() -> None:
    """BreakKind 限定 4 種 enum-like literal。"""
    from smc_features.types import StructureBreak

    for k in ("BOS_BULL", "BOS_BEAR", "CHOCH_BULL", "CHOCH_BEAR"):
        sb = StructureBreak(
            kind=k,  # type: ignore[arg-type]
            time=np.datetime64("2024-03-15T00:00:00"),
            bar_index=1,
            break_price=100.0,
            anchor_swing_time=np.datetime64("2024-03-14T00:00:00"),
            anchor_swing_bar_index=0,
            anchor_swing_price=99.0,
            trend_after="bullish",
        )
        assert sb.kind == k


def test_order_block_v2_adds_source_break_fields() -> None:
    """OrderBlock 應新增 source_break_index、source_break_kind 兩欄位（FR-009）。"""
    from smc_features.types import OrderBlock

    fields = {f.name for f in dataclasses.fields(OrderBlock)}
    assert "source_break_index" in fields, "OrderBlock 缺 source_break_index"
    assert "source_break_kind" in fields, "OrderBlock 缺 source_break_kind"


def test_smc_feature_params_v2_has_fvg_min_atr_ratio() -> None:
    """SMCFeatureParams 應新增 fvg_min_atr_ratio: float = 0.25（FR-011）。"""
    from smc_features.types import SMCFeatureParams

    p = SMCFeatureParams()
    assert hasattr(p, "fvg_min_atr_ratio")
    assert p.fvg_min_atr_ratio == 0.25


def test_smc_feature_params_v2_rejects_negative_atr_ratio() -> None:
    """fvg_min_atr_ratio < 0 應拋 ValueError（與其他 param 區間檢驗一致）。"""
    from smc_features.types import SMCFeatureParams

    with pytest.raises(ValueError, match="fvg_min_atr_ratio"):
        SMCFeatureParams(fvg_min_atr_ratio=-0.1)


def test_batch_result_has_breaks_field() -> None:
    """BatchResult 應有 breaks: tuple[StructureBreak, ...] 欄位（FR-007）。"""
    from smc_features.types import BatchResult

    fields = {f.name for f in dataclasses.fields(BatchResult)}
    assert "breaks" in fields, "BatchResult 缺 breaks 欄位"
