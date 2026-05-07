"""T033 — ``visualize`` 簽章與 contracts/api.pyi 對齊。"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from smc_features import visualize


def test_visualize_signature_matches_contract():
    sig = inspect.signature(visualize)
    params = sig.parameters

    assert list(params)[:4] == [
        "df_with_features",
        "time_range",
        "output_path",
        "fmt",
    ]
    assert params["fmt"].default == "png"
    assert params["fmt"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    # params is keyword-only with default None
    assert params["params"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["params"].default is None
    # 回傳 None
    assert sig.return_annotation in (None, type(None), "None")


def test_visualize_rejects_invalid_fmt(tmp_path: Path):
    df = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]},
        index=pd.DatetimeIndex(["2024-01-02"]),
    )
    with pytest.raises(ValueError):
        visualize(df, (df.index[0], df.index[0]), tmp_path / "x.svg", fmt="svg")  # type: ignore[arg-type]
