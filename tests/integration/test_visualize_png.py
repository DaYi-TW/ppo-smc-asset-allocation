"""T031 — visualize PNG 後端驗證（spec FR-009、SC-005）。"""

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


def test_png_file_created_and_loadable(tmp_path: Path, fixture_df: pd.DataFrame):
    pytest.importorskip("PIL")
    from PIL import Image

    out = tmp_path / "smc.png"
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=True)
    visualize(
        br.output,
        (br.output.index[10], br.output.index[60]),
        out,
        fmt="png",
        params=SMCFeatureParams(),
    )
    assert out.exists()
    assert out.stat().st_size > 10_000
    img = Image.open(out)
    img.load()  # 強制解碼，失敗代表 PNG 結構壞掉。
    assert img.size[0] > 100 and img.size[1] > 100


def test_png_rejects_time_range_out_of_bounds(tmp_path: Path, fixture_df: pd.DataFrame):
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=True)
    end = br.output.index[-1]
    too_late = end + pd.Timedelta(days=365)
    with pytest.raises(ValueError):
        visualize(
            br.output,
            (br.output.index[0], too_late),
            tmp_path / "x.png",
            fmt="png",
        )


def test_png_rejects_missing_aux(tmp_path: Path, fixture_df: pd.DataFrame):
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=False)
    with pytest.raises(ValueError):
        visualize(
            br.output,
            (br.output.index[0], br.output.index[10]),
            tmp_path / "x.png",
            fmt="png",
        )


def test_png_rejects_missing_parent_dir(tmp_path: Path, fixture_df: pd.DataFrame):
    br = batch_compute(fixture_df, SMCFeatureParams(), include_aux=True)
    out = tmp_path / "missing_dir" / "smc.png"
    with pytest.raises(ValueError):
        visualize(br.output, (br.output.index[0], br.output.index[10]), out)
