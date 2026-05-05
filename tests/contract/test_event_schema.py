"""StructureBreak JSON Schema 合規測試。

對應 Constitution Gate IV-2（cross-tier serialization 契約）、
specs/008-smc-engine-v2/contracts/structure_break.schema.json。
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "008-smc-engine-v2"
    / "contracts"
    / "structure_break.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_file_loads_as_valid_json(schema: dict) -> None:
    assert schema["title"] == "StructureBreak"
    assert schema["$schema"].startswith("https://json-schema.org/")


def test_schema_examples_validate(schema: dict) -> None:
    """schema['examples'] 內每筆示例 instance 都應通過 schema 自身驗證。"""
    assert "examples" in schema and len(schema["examples"]) >= 2
    for example in schema["examples"]:
        jsonschema.validate(instance=example, schema=schema)


def test_schema_rejects_invalid_kind(schema: dict) -> None:
    bad = dict(schema["examples"][0])
    bad["kind"] = "BOS_SIDEWAYS"  # 不在 enum 中
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_schema_rejects_missing_required_field(schema: dict) -> None:
    bad = dict(schema["examples"][0])
    del bad["trend_after"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_schema_rejects_negative_bar_index(schema: dict) -> None:
    bad = dict(schema["examples"][0])
    bad["bar_index"] = -1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_structure_break_dataclass_serializes_to_schema(schema: dict) -> None:
    """v2 落地後，StructureBreak instance 用 dataclasses.asdict + 時間轉 ISO
    後應通過 schema 驗證——保證跨層 serialization 契約。"""
    import dataclasses

    import numpy as np

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
    raw = dataclasses.asdict(sb)
    raw["time"] = str(raw["time"]).split(".")[0]
    raw["anchor_swing_time"] = str(raw["anchor_swing_time"]).split(".")[0]
    jsonschema.validate(instance=raw, schema=schema)
