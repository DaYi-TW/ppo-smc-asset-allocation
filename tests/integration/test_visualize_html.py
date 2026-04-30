"""T032 — visualize HTML 後端驗證（spec FR-009、SC-005）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from smc_features import SMCFeatureParams, batch_compute, visualize


@pytest.fixture
def fixture_df() -> pd.DataFrame:
    path = Path("tests/fixtures/nvda_2024H1.parquet")
    if not path.exists():
        pytest.skip(f"fixture {path} 不存在；先跑 scripts/build_smc_fixtures.py")
    return pd.read_parquet(path)


def test_html_file_created_and_contains_plotly(tmp_path: Path, fixture_df: pd.DataFrame):
    out = tmp_path / "smc.html"
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=True)
    visualize(
        br.output,
        (br.output.index[10], br.output.index[60]),
        out,
        fmt="html",
        params=SMCFeatureParams(),
    )
    assert out.exists()
    assert out.stat().st_size > 5_000
    text = out.read_text(encoding="utf-8", errors="ignore")
    # plotly 通常會將 plotly-graph-div 或 plotly.js bundle 名稱放進 HTML
    assert "plotly" in text.lower()
    # 確認非 mplfinance 後端 — 不應出現 mplfinance 字樣
    assert "mplfinance" not in text.lower()


def test_html_contains_signal_text_when_present(tmp_path: Path, fixture_df: pd.DataFrame):
    out = tmp_path / "smc.html"
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=True)
    visualize(
        br.output,
        (br.output.index[0], br.output.index[-1]),
        out,
        fmt="html",
    )
    text = out.read_text(encoding="utf-8", errors="ignore")
    has_signal = ((br.output["bos_signal"].fillna(0) != 0).any()) or (
        (br.output["choch_signal"].fillna(0) != 0).any()
    )
    if has_signal:
        assert ("BOS" in text) or ("CHoCh" in text)


def test_html_rejects_missing_aux(tmp_path: Path, fixture_df: pd.DataFrame):
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=False)
    with pytest.raises(ValueError):
        visualize(
            br.output,
            (br.output.index[0], br.output.index[10]),
            tmp_path / "x.html",
            fmt="html",
        )
