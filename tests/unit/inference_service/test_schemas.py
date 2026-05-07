"""T010 — PredictionPayload Pydantic schema 對齊 predict.py JSON (RED → GREEN at T014).

對應 spec FR-006 / FR-007 / SC-005.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

_PREDICT_JSON_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "runs"
    / "20260506_004455_659b8eb_seed42"
    / "prediction_2026-04-28.json"
)


def _base_payload_dict() -> dict:
    """以既存 predict.py JSON 為基礎、補上 005 三個新欄位。"""
    base = json.loads(_PREDICT_JSON_FIXTURE.read_text(encoding="utf-8"))
    base["triggered_by"] = "manual"
    base["inference_id"] = str(uuid.uuid4())
    base["inferred_at_utc"] = datetime.now(UTC).isoformat()
    return base


@pytest.mark.skipif(not _PREDICT_JSON_FIXTURE.exists(), reason="prediction fixture missing")
def test_payload_validates_predict_py_json() -> None:
    """既存 predict.py 輸出 + 三個新欄位 → 驗證通過."""
    from inference_service.schemas import PredictionPayload

    payload = PredictionPayload.model_validate(_base_payload_dict())

    assert payload.as_of_date == "2026-04-28"
    assert payload.deterministic is True
    assert payload.weights_capped is False
    assert payload.renormalized is False
    assert payload.triggered_by == "manual"
    assert payload.context.include_smc is True
    assert payload.context.n_warmup_steps == 2090


@pytest.mark.skipif(not _PREDICT_JSON_FIXTURE.exists(), reason="prediction fixture missing")
def test_target_weights_sum_to_one_in_simplex() -> None:
    """7 維 weights ∈ [0,1] 且 sum ≈ 1（容差 1e-5，浮點 round-trip）."""
    from inference_service.schemas import PredictionPayload

    payload = PredictionPayload.model_validate(_base_payload_dict())
    weights = payload.target_weights

    weight_values = [
        weights.NVDA, weights.AMD, weights.TSM, weights.MU,
        weights.GLD, weights.TLT, weights.CASH,
    ]
    for w in weight_values:
        assert 0.0 <= w <= 1.0, f"weight out of [0,1]: {w}"
    assert math.isclose(sum(weight_values), 1.0, abs_tol=1e-5)


def test_payload_rejects_invalid_triggered_by() -> None:
    """triggered_by 必須 in {scheduled, manual}."""
    from inference_service.schemas import PredictionPayload

    bad = _base_payload_dict()
    bad["triggered_by"] = "cosmic_ray"
    with pytest.raises(ValidationError, match="triggered_by"):
        PredictionPayload.model_validate(bad)


def test_payload_rejects_weight_out_of_range() -> None:
    """weights_capped 該設 True 時若放任 weight > 1.0 → ValidationError."""
    from inference_service.schemas import PredictionPayload

    bad = _base_payload_dict()
    bad["target_weights"]["NVDA"] = 1.5
    with pytest.raises(ValidationError):
        PredictionPayload.model_validate(bad)


def test_payload_round_trip_json_serialize() -> None:
    """model → JSON → dict → model 不變."""
    from inference_service.schemas import PredictionPayload

    original = PredictionPayload.model_validate(_base_payload_dict())
    serialized = original.model_dump(mode="json")
    restored = PredictionPayload.model_validate(serialized)
    assert original == restored
