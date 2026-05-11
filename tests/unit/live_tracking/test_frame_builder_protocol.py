"""T018 — LiveFrameBuilder Protocol conformance + DATA_FETCH hook test.

Full end-to-end LiveFrameBuilder（policy.predict + env rollout + build_episode_artifact）
needs torch + a PPO zip + ``data/raw`` parquet — those run in Docker, not pytest.

This unit test covers two things that don't need torch:

1. ``LiveFrameBuilder`` is callable and conforms to ``FrameBuilder`` Protocol。
2. ``LIVE_TRACKER_FORCE_FETCH_ERROR`` env hook raises ``DataFetchError``
   without touching policy/data — used by integration tests (T057 quickstart §8).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import inspect

from live_tracking.frame_builder import LiveFrameBuilder
from live_tracking.pipeline import DataFetchError


def test_live_frame_builder_signature_matches_protocol() -> None:
    """LiveFrameBuilder.__call__ 簽名符合 FrameBuilder Protocol（kwargs-only）。"""
    builder = LiveFrameBuilder(
        policy_path=Path("/nonexistent/policy.zip"),
        data_root=Path("/nonexistent/data"),
        policy_run_id="test_run",
    )
    assert callable(builder)
    sig = inspect.signature(builder.__call__)
    params = sig.parameters
    expected = {"current_envelope", "missing_days", "initial_nav", "start_anchor"}
    assert expected.issubset(params.keys()), (
        f"missing protocol kwargs: {expected - params.keys()}"
    )
    # 所有 4 個必須是 keyword-only（pipeline 用 kwargs 呼叫）
    for name in expected:
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{name!r} is not keyword-only"
        )


def test_force_fetch_error_env_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """LIVE_TRACKER_FORCE_FETCH_ERROR 環境變數 → 直接 raise DataFetchError。"""
    monkeypatch.setenv("LIVE_TRACKER_FORCE_FETCH_ERROR", "1")
    builder = LiveFrameBuilder(
        policy_path=Path("/nonexistent/policy.zip"),
        data_root=Path("/nonexistent/data"),
        policy_run_id="test_run",
    )
    with pytest.raises(DataFetchError, match="forced via"):
        builder(
            current_envelope=None,
            missing_days=[date(2026, 4, 30)],
            initial_nav=1.0,
            start_anchor=date(2026, 4, 29),
        )
