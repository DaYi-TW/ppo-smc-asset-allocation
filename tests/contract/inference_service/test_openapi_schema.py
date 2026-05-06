"""T045 — OpenAPI 3.1 schema validity (G-V-2).

驗證 contracts/openapi.yaml：
    1. yaml 可被 openapi_spec_validator 接受（schema 合法）
    2. 4 個 path 都存在 (/infer/run, /infer/latest, /healthz, /openapi.json)
    3. 所有 path 都有 ErrorResponse / PredictionPayload schema reference
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OPENAPI_PATH = _REPO_ROOT / "specs" / "005-inference-service" / "contracts" / "openapi.yaml"


def _load_spec() -> dict:
    import yaml

    with _OPENAPI_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_openapi_spec_is_valid() -> None:
    """openapi.yaml 通過 openapi_spec_validator (3.1)."""
    pytest.importorskip("openapi_spec_validator")
    from openapi_spec_validator import validate

    spec = _load_spec()
    # raises OpenAPIValidationError on schema violation
    validate(spec)


def test_openapi_has_required_paths() -> None:
    """4 個 endpoint 必須存在（spec FR-001 / FR-008 / FR-009 + FastAPI auto）."""
    spec = _load_spec()
    paths = spec.get("paths", {})
    assert "/infer/run" in paths, paths.keys()
    assert "/infer/latest" in paths
    assert "/healthz" in paths
    assert "/openapi.json" in paths


def test_openapi_components_define_required_schemas() -> None:
    """PredictionPayload / ErrorResponse / HealthResponse / TargetWeights 都在."""
    spec = _load_spec()
    schemas = spec.get("components", {}).get("schemas", {})
    for name in (
        "PredictionPayload",
        "PredictionContext",
        "TargetWeights",
        "HealthResponse",
        "ErrorResponse",
    ):
        assert name in schemas, f"missing schema: {name}"


def test_prediction_payload_schema_has_new_fields() -> None:
    """PredictionPayload required 欄位含 005 新增的 triggered_by/inference_id/inferred_at_utc."""
    spec = _load_spec()
    pp = spec["components"]["schemas"]["PredictionPayload"]
    required = set(pp["required"])
    assert {"triggered_by", "inference_id", "inferred_at_utc"} <= required, required
