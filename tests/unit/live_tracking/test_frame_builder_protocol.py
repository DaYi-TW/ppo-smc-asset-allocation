"""T018 — LiveFrameBuilder Protocol conformance + DATA_FETCH hook test.

Full end-to-end LiveFrameBuilder（policy.predict + env rollout + build_episode_artifact）
needs torch + a PPO zip + ``data/raw`` parquet — those run in Docker, not pytest.

This unit test covers three things that don't need torch:

1. ``LiveFrameBuilder`` is callable and conforms to ``FrameBuilder`` Protocol。
2. ``LIVE_TRACKER_FORCE_FETCH_ERROR`` env hook raises ``DataFetchError``
   without touching policy/data — used by integration tests (T057 quickstart §8).
3. ``__call__`` rescales kept-window NAVs so ``frame[0].nav == initial_nav``
   (spec FR-002 = 1.7291986). Without this, frame 0 NAV is the 2018→2026
   cumulative env-state (≈$216), which drifts by float64 noise across every
   data/raw refresh and breaks the append-only invariant.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from typing import Any

import pytest

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


class _StubRecord:
    """Minimal TrajectoryRecord stand-in for the rescale unit test.

    Real TrajectoryRecord lives in ``ppo_training.trajectory_writer`` and
    pulls torch/numpy at import time — avoid that here so the test stays
    isolated to the rescale arithmetic.
    """

    __slots__ = ("date", "step", "nav", "log_return")

    def __init__(self, d: str, nav: float, log_return: float = 0.0) -> None:
        self.date = d
        self.step = 0
        self.nav = nav
        self.log_return = log_return


def test_call_rescales_kept_window_nav_to_initial_nav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """frame[0].nav 必須等於 initial_nav；後續 frames 等比例縮放（保持 log_return）。

    Regression for 2026-05-13 incident：env 從 2018-01-02 reset → 2026-04-29
    時 NAV 已累積到 ~$216，每次 data/raw 刷新都會讓這個 ~$216 漂移幾分錢，
    INV-3 append-only guard 開火 → live tracking 卡住、前端拿到 stale data。
    """
    builder = LiveFrameBuilder(
        policy_path=Path("/nonexistent/policy.zip"),
        data_root=Path("/nonexistent/data"),
        policy_run_id="test_run",
    )

    # Simulate env rollout from 2018 → 2026: frame 0 NAV is the 8-year
    # compounded value, not the spec-mandated 1.7291986 anchor.
    raw_records = [
        _StubRecord("2026-04-29", nav=216.4402, log_return=0.0),
        _StubRecord("2026-04-30", nav=216.8974, log_return=0.00211),
        _StubRecord("2026-05-01", nav=217.7775, log_return=0.00405),
    ]
    summary = {"n_steps": 2}

    def fake_rollout(self: Any, target_date: date) -> tuple[list[Any], dict[str, Any]]:
        return raw_records, summary

    captured: dict[str, Any] = {}

    def fake_build_envelope(
        self: Any,
        records: list[Any],
        summary_payload: dict[str, Any],
        start_anchor: date,
    ) -> Any:
        # Snapshot what we hand off to the artifact builder.
        captured["records"] = list(records)
        captured["summary"] = dict(summary_payload)
        # Return a stub envelope (callers only mutate id/policyId on it).
        class _StubEnvelope:
            class _S:
                id = "x"
                policyId = "x"
            summary = _S()
        return _StubEnvelope()

    monkeypatch.setattr(
        LiveFrameBuilder, "_run_env_to_target", fake_rollout, raising=True
    )
    monkeypatch.setattr(
        LiveFrameBuilder,
        "_build_envelope_via_artifact_builder",
        fake_build_envelope,
        raising=True,
    )
    # _patch_summary_for_live touches numpy + ppo_training.evaluate; stub
    # it to a pass-through so this unit test stays import-light.
    monkeypatch.setattr(
        LiveFrameBuilder,
        "_patch_summary_for_live",
        staticmethod(lambda s, r: s),
        raising=True,
    )

    initial_nav = 1.7291986
    builder(
        current_envelope=None,
        missing_days=[date(2026, 5, 1)],
        initial_nav=initial_nav,
        start_anchor=date(2026, 4, 29),
    )

    out_records = captured["records"]
    assert len(out_records) == 3
    # Frame 0 MUST equal initial_nav exactly (spec FR-002).
    assert out_records[0].nav == pytest.approx(initial_nav, abs=1e-12)
    # Ratio preservation (the whole point — log_returns stay valid).
    scale = initial_nav / 216.4402
    assert out_records[1].nav == pytest.approx(216.8974 * scale, rel=1e-9)
    assert out_records[2].nav == pytest.approx(217.7775 * scale, rel=1e-9)
    # log_return is scale-invariant — must NOT be touched.
    assert out_records[1].log_return == pytest.approx(0.00211, abs=1e-12)
    assert out_records[2].log_return == pytest.approx(0.00405, abs=1e-12)
