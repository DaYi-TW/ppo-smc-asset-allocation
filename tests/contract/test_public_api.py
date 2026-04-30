"""Contract: data_ingestion package re-exports the full api.pyi surface.

This guards against accidental drift between the documented public API and
the actual import-time module surface. If a name is renamed or removed in
api.pyi without a MAJOR bump, this test fails before downstream features
(001-smc-feature-engine, 003-environment) hit the change at runtime.
"""

from __future__ import annotations

import inspect

import data_ingestion

EXPECTED_NAMES = {
    "IngestionConfig",
    "ColumnSchema",
    "IndexSchema",
    "TimeRange",
    "QualitySummary",
    "SnapshotMetadata",
    "VerifyResult",
    "load_asset_snapshot",
    "load_rate_snapshot",
    "load_metadata",
    "verify_snapshot",
    "verify_all",
}


def test_all_lists_documented_surface() -> None:
    assert set(data_ingestion.__all__) == EXPECTED_NAMES


def test_every_documented_name_is_resolvable() -> None:
    for name in EXPECTED_NAMES:
        assert hasattr(data_ingestion, name), f"missing public symbol: {name}"


def test_dataclass_symbols_are_classes() -> None:
    dataclass_names = {
        "IngestionConfig",
        "ColumnSchema",
        "IndexSchema",
        "TimeRange",
        "QualitySummary",
        "SnapshotMetadata",
        "VerifyResult",
    }
    for name in dataclass_names:
        sym = getattr(data_ingestion, name)
        assert inspect.isclass(sym), f"{name} should be a class, got {type(sym)!r}"


def test_function_symbols_are_callable() -> None:
    function_names = {
        "load_asset_snapshot",
        "load_rate_snapshot",
        "load_metadata",
        "verify_snapshot",
        "verify_all",
    }
    for name in function_names:
        sym = getattr(data_ingestion, name)
        assert callable(sym), f"{name} should be callable, got {type(sym)!r}"


def test_ingestion_config_is_frozen() -> None:
    cfg = data_ingestion.IngestionConfig()
    try:
        cfg.start_date = "2020-01-01"  # type: ignore[misc]
    except (AttributeError, Exception) as exc:
        assert "frozen" in str(exc).lower() or isinstance(exc, AttributeError)
    else:
        raise AssertionError("IngestionConfig must be frozen but accepted attribute write")


def test_ingestion_config_validates_date_order() -> None:
    import pytest

    with pytest.raises(ValueError, match="start_date"):
        data_ingestion.IngestionConfig(start_date="2026-01-01", end_date="2020-01-01")


def test_ingestion_config_rejects_duplicate_tickers() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        data_ingestion.IngestionConfig(
            tickers_risk_on=("NVDA", "NVDA"), tickers_risk_off=("GLD",)
        )
