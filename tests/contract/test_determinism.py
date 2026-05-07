"""T021a — spec FR-007 不依賴系統時間 / 隨機性 / 多執行緒 reduce。

(a) 靜態斷言：``smc_features`` 套件 `.py` 檔不在計算路徑 import
    ``random | secrets | datetime``（``time`` 允許用於非計算路徑）。
(b) 行為斷言：mock ``time.time`` / ``random.seed`` 包裹 ``batch_compute``，
    輸出仍 byte-identical。
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from smc_features import batch_compute

PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "smc_features"
FORBIDDEN = {"random", "secrets", "datetime"}


def _module_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_forbidden_imports_in_compute_path():
    """除 viz/ 子套件外，計算路徑禁止匯入隨機 / 系統時間模組。"""
    offenders: list[tuple[Path, set[str]]] = []
    for py in PKG_ROOT.rglob("*.py"):
        # viz 子套件允許用 datetime 做圖例日期；計算路徑（非 viz）才禁止。
        if "viz" in py.parts:
            continue
        bad = _module_imports(py) & FORBIDDEN
        if bad:
            offenders.append((py, bad))
    assert not offenders, f"計算路徑禁止匯入 {FORBIDDEN}: {offenders}"


def test_byte_identical_under_mocked_clock_and_random(small_ohlcv, default_params):
    a = batch_compute(small_ohlcv, default_params).output
    with patch("time.time", return_value=0.0):
        random.seed(123456)
        b = batch_compute(small_ohlcv, default_params).output
    pd.testing.assert_frame_equal(a, b, check_dtype=True, check_exact=True)
