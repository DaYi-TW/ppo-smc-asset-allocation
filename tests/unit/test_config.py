"""IngestionConfig 驗證 — config.py 各 raise 路徑。"""

from __future__ import annotations

import pytest

from data_ingestion import IngestionConfig


def test_default_config_constructs():
    cfg = IngestionConfig()
    assert cfg.start_date == "2018-01-01"
    assert len(cfg.all_tickers()) == 6


def test_invalid_iso_date_format_rejected():
    with pytest.raises(ValueError, match="ISO 8601"):
        IngestionConfig(start_date="2024/01/01", end_date="2024-01-31")


def test_invalid_calendar_date_rejected():
    # 形式正確但日期不合法（2 月 30 日）
    with pytest.raises(ValueError, match="not a valid calendar date"):
        IngestionConfig(start_date="2024-02-30", end_date="2024-12-31")


def test_start_after_end_rejected():
    with pytest.raises(ValueError, match=r"start_date.*must be <="):
        IngestionConfig(start_date="2024-12-31", end_date="2024-01-01")


def test_empty_tickers_rejected():
    with pytest.raises(ValueError, match="at least one ticker"):
        IngestionConfig(tickers_risk_on=(), tickers_risk_off=())


def test_lowercase_ticker_rejected():
    with pytest.raises(ValueError, match="uppercase alphanumeric"):
        IngestionConfig(tickers_risk_on=("nvda",), tickers_risk_off=("GLD",))


def test_duplicate_ticker_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        IngestionConfig(
            tickers_risk_on=("NVDA", "NVDA"),
            tickers_risk_off=("GLD",),
        )


def test_empty_fred_series_id_rejected():
    with pytest.raises(ValueError, match="fred_series_id"):
        IngestionConfig(fred_series_id="   ")


def test_zero_retry_attempts_rejected():
    with pytest.raises(ValueError, match="max_retry_attempts"):
        IngestionConfig(max_retry_attempts=0)


def test_zero_retry_base_seconds_rejected():
    with pytest.raises(ValueError, match="retry_base_seconds"):
        IngestionConfig(retry_base_seconds=0.0)


def test_low_retry_multiplier_rejected():
    with pytest.raises(ValueError, match="retry_multiplier"):
        IngestionConfig(retry_multiplier=0.5)
