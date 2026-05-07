"""sources/yfinance_source.py + sources/fred_source.py 單元測試。

不依賴網路：透過 monkeypatch 把模組層的 ``yf`` / ``Fred`` 替換為 stub，覆蓋
``fetch_yfinance`` / ``fetch_fred`` 的所有錯誤路徑與成功路徑。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from data_ingestion.sources import fred_source, yfinance_source
from data_ingestion.sources.fred_source import (
    FredApiKeyMissingError,
    FredFetchError,
    fetch_fred,
)
from data_ingestion.sources.yfinance_source import (
    YfinanceFetchError,
    _normalise_yfinance_frame,
    fetch_yfinance,
)

# ---------------------------------------------------------------------------
# yfinance_source
# ---------------------------------------------------------------------------


class _FakeYf:
    """Stand-in for yfinance with a configurable download() outcome."""

    def __init__(self, df: pd.DataFrame | None = None, raises: Exception | None = None):
        self._df = df
        self._raises = raises

    def download(self, **kwargs: Any) -> pd.DataFrame | None:
        if self._raises is not None:
            raise self._raises
        return self._df


def _good_yf_frame(n: int = 4) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", name="Date")
    return pd.DataFrame(
        {
            "Open": np.linspace(100, 103, n),
            "High": np.linspace(101, 104, n),
            "Low": np.linspace(99, 102, n),
            "Close": np.linspace(100.5, 103.5, n),
            "Volume": np.array([1_000_000] * n, dtype="int64"),
        },
        index=idx,
    )


def test_fetch_yfinance_yf_not_installed_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(yfinance_source, "yf", None)
    with pytest.raises(YfinanceFetchError, match="not installed"):
        fetch_yfinance("NVDA", "2024-01-02", "2024-01-12")


def test_fetch_yfinance_empty_frame_raises_with_ticker(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(yfinance_source, "yf", _FakeYf(df=pd.DataFrame()))
    with pytest.raises(YfinanceFetchError, match="NVDA"):
        fetch_yfinance("NVDA", "2024-01-02", "2024-01-12", max_attempts=1, base_seconds=0.01)


def test_fetch_yfinance_none_response_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(yfinance_source, "yf", _FakeYf(df=None))
    with pytest.raises(YfinanceFetchError):
        fetch_yfinance("NVDA", "2024-01-02", "2024-01-12", max_attempts=1, base_seconds=0.01)


def test_fetch_yfinance_unexpected_exception_wrapped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(yfinance_source, "yf", _FakeYf(raises=RuntimeError("boom")))
    with pytest.raises(YfinanceFetchError, match="fatal error"):
        fetch_yfinance("NVDA", "2024-01-02", "2024-01-12", max_attempts=1, base_seconds=0.01)


def test_fetch_yfinance_retry_exhausted_wrapped(monkeypatch: pytest.MonkeyPatch):
    """ConnectionError → tenacity 重試 → 達上限 → 重新拋出，由 fatal-error 分支包覆。"""
    monkeypatch.setattr(
        yfinance_source,
        "yf",
        _FakeYf(raises=ConnectionError("net down")),
    )
    with pytest.raises(YfinanceFetchError, match="fatal error"):
        fetch_yfinance(
            "NVDA",
            "2024-01-02",
            "2024-01-12",
            max_attempts=2,
            base_seconds=0.001,
            multiplier=1.1,
        )


def test_fetch_yfinance_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(yfinance_source, "yf", _FakeYf(df=_good_yf_frame()))
    df, params = fetch_yfinance("NVDA", "2024-01-02", "2024-01-12")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "date"
    assert df.dtypes["volume"].name == "int64"
    assert df.dtypes["close"].name == "float64"
    # call_params 應記錄 verbatim 呼叫 + end+1day exclusive
    assert params["ticker"] == "NVDA"
    assert params["end"] == "2024-01-13"  # exclusive bound
    assert params["auto_adjust"] is True


def test_normalise_yfinance_frame_drops_multiindex():
    base = _good_yf_frame()
    base.columns = pd.MultiIndex.from_tuples([(c, "NVDA") for c in base.columns])
    out = _normalise_yfinance_frame(base, "NVDA")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]


def test_normalise_yfinance_frame_strips_tz():
    base = _good_yf_frame()
    base.index = base.index.tz_localize("UTC")
    out = _normalise_yfinance_frame(base, "NVDA")
    assert out.index.tz is None


def test_normalise_yfinance_frame_missing_columns_raises():
    bad = _good_yf_frame().drop(columns=["Volume"])
    with pytest.raises(YfinanceFetchError, match="missing columns"):
        _normalise_yfinance_frame(bad, "NVDA")


# ---------------------------------------------------------------------------
# fred_source
# ---------------------------------------------------------------------------


class _FakeFredClient:
    def __init__(self, series: pd.Series | None = None, raises: Exception | None = None):
        self._series = series
        self._raises = raises

    def get_series(self, _series_id: str, **kwargs: Any) -> pd.Series | None:
        if self._raises is not None:
            raise self._raises
        return self._series


def _make_fake_fred_factory(client: _FakeFredClient):
    def _factory(api_key: str) -> _FakeFredClient:
        assert api_key == "test-key"
        return client

    return _factory


def test_fetch_fred_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(FredApiKeyMissingError, match="FRED_API_KEY"):
        fetch_fred("DTB3", "2024-01-02", "2024-01-12")


def test_fetch_fred_message_includes_registration_url():
    err = FredApiKeyMissingError()
    assert "fred.stlouisfed.org" in str(err)


def test_fetch_fred_fredapi_not_installed_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(fred_source, "Fred", None)
    with pytest.raises(FredFetchError, match="not installed"):
        fetch_fred("DTB3", "2024-01-02", "2024-01-12")


def test_fetch_fred_empty_series_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(
        fred_source,
        "Fred",
        _make_fake_fred_factory(_FakeFredClient(series=pd.Series([], dtype="float64"))),
    )
    with pytest.raises(FredFetchError, match="empty series"):
        fetch_fred("DTB3", "2024-01-02", "2024-01-12", max_attempts=1, base_seconds=0.001)


def test_fetch_fred_unexpected_exception_wrapped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(
        fred_source, "Fred", _make_fake_fred_factory(_FakeFredClient(raises=RuntimeError("boom")))
    )
    with pytest.raises(FredFetchError, match="fatal error"):
        fetch_fred("DTB3", "2024-01-02", "2024-01-12", max_attempts=1, base_seconds=0.001)


def test_fetch_fred_retry_exhausted_wrapped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(
        fred_source,
        "Fred",
        _make_fake_fred_factory(_FakeFredClient(raises=ConnectionError("net down"))),
    )
    with pytest.raises(FredFetchError, match="fatal error"):
        fetch_fred(
            "DTB3",
            "2024-01-02",
            "2024-01-12",
            max_attempts=2,
            base_seconds=0.001,
            multiplier=1.1,
        )


def test_fetch_fred_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    series = pd.Series(np.linspace(5.20, 5.30, 5), index=idx)
    monkeypatch.setattr(
        fred_source, "Fred", _make_fake_fred_factory(_FakeFredClient(series=series))
    )
    out, params = fetch_fred("DTB3", "2024-01-02", "2024-01-12")
    assert out.name == "rate_pct"
    assert out.index.name == "date"
    assert out.dtype.name == "float64"
    assert params["series_id"] == "DTB3"
    assert params["observation_start"] == "2024-01-02"
    assert params["observation_end"] == "2024-01-12"


def test_fetch_fred_strips_tz_aware_index(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    idx = pd.date_range("2024-01-02", periods=3, freq="B", tz="UTC")
    series = pd.Series([5.20, 5.25, 5.30], index=idx)
    monkeypatch.setattr(
        fred_source, "Fred", _make_fake_fred_factory(_FakeFredClient(series=series))
    )
    out, _ = fetch_fred("DTB3", "2024-01-02", "2024-01-12")
    assert out.index.tz is None


def test_fetch_fred_explicit_api_key_overrides_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    idx = pd.date_range("2024-01-02", periods=3, freq="B")
    series = pd.Series([5.20, 5.25, 5.30], index=idx)
    monkeypatch.setattr(
        fred_source, "Fred", _make_fake_fred_factory(_FakeFredClient(series=series))
    )
    out, _ = fetch_fred("DTB3", "2024-01-02", "2024-01-12", api_key="test-key")
    assert len(out) == 3
