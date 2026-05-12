"""T015~T022 — Daily tracker pipeline orchestration.

對應 spec 010 FR-007 / FR-008 / FR-009 / FR-010 / FR-011 / FR-019 / FR-020 /
FR-026 與 data-model §3 (DailyTrackerPipelineRun)。

Pipeline 階段（research §R3）::

    1. guard            : status.is_running ⇒ raise RefreshInProgressError
    2. mark_running     : status.mark_running(pid, started_at) + persist
    3. compute missing  : calendar.missing_trading_days(...)
    4. early return     : empty ⇒ mark_succeeded(last_frame_date 不變) + log + return
    5. compute frames   : 透過 ``compute_new_frames`` callback 跑
                          fetch → inference → env step → 收 frame list
                          異常 ⇒ mark_failed("INFERENCE: ...") raise
    6. append + recompute: 對整段 trajectory 重算 SMC overlay + summary metrics
                          異常 ⇒ mark_failed("INFERENCE: ...") raise
    7. atomic write     : store.atomic_write(envelope)
                          異常 ⇒ mark_failed("WRITE: ...") raise
    8. mark_succeeded   : status.mark_succeeded(last_frame_date=frames[-1].date)
                          + structured log

Error class taxonomy (research §R10): three prefixes for ``last_error``：
* ``DATA_FETCH:`` — yfinance / FRED 拿不到資料
* ``INFERENCE:`` — env / policy / SMC 計算錯誤
* ``WRITE:``     — atomic write / fsync / disk full

Constitution Principle III gate（NON-NEGOTIABLE）：``compute_new_frames`` 內必
須使用 ``portfolio_env.reward.compute_reward_components`` 計算每個 frame 的
reward.{return, drawdown_penalty, cost_penalty}。不得自行實作。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from inference_service.episode_schemas import EpisodeDetail

from .calendar import missing_trading_days
from .status import LiveTrackingStatus
from .store import LiveTrackingStore

logger = logging.getLogger(__name__)


# ---------- Errors ----------


class RefreshInProgressError(RuntimeError):
    """Raised when status.is_running=True at pipeline entry — single-flight."""


class DataFetchError(RuntimeError):
    """OHLCV / FRED fetch failed — maps to last_error 'DATA_FETCH:' prefix."""


class InferenceError(RuntimeError):
    """env / policy / SMC compute failed — maps to 'INFERENCE:' prefix."""


class WriteError(RuntimeError):
    """atomic_write / fsync failed — maps to 'WRITE:' prefix."""


# ---------- Pipeline output ----------


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of one ``DailyTrackerPipeline.run_once`` invocation.

    Mirrors data-model §3 ``DailyTrackerPipelineRun`` (subset — not persisted)。
    """

    pipeline_id: str
    frames_appended: int
    smc_zones_computed: int
    pipeline_duration_ms: int
    final_status: str  # "succeeded" | "failed_data_fetch" | "failed_inference" | "failed_write" | "noop"
    last_frame_date: date | None
    error_message: str | None = None


# ---------- Frame builder Protocol ----------


class FrameBuilder(Protocol):
    """Callback signature for the per-day inference loop。

    Pipeline 把 (current_envelope, missing_days) 交給 builder，後者負責：

    1. 從 envelope 最後一個 frame 復原 env state（reset env to that NAV/weights）
    2. 對每個 missing day：fetch OHLCV → predict action → env.step →
       build TrajectoryFrame（reward 三元、ohlcvByAsset、smcSignals 暫填）
    3. 跑 008 ``batch_compute_events`` over the full trajectory → 重算
       smcOverlayByAsset
    4. 重算 EpisodeSummary（finalNav / cumReturn / MDD / Sharpe / Sortino）
    5. 回傳更新後的 EpisodeDetail（不 mutate input）

    Builder 是 protocol — 真實實作在 pipeline 注入時提供（單元測試可塞 stub）。
    """

    def __call__(
        self,
        *,
        current_envelope: EpisodeDetail | None,
        missing_days: list[date],
        initial_nav: float,
        start_anchor: date,
    ) -> EpisodeDetail: ...


# ---------- Pipeline ----------


@dataclass
class DailyTrackerPipeline:
    """Orchestrate one daily tracker refresh — see module docstring。

    Attributes:
        store: ``LiveTrackingStore`` for ``live_tracking.json``。
        status_path: Path to ``live_tracking_status.json``。
        build_frames: ``FrameBuilder`` callback — injected so unit tests can
            stub fetch/inference/SMC without touching real OHLCV / policy。
        initial_nav: Live tracking 起始 NAV（spec FR-002 = 1.7291986）。
        start_anchor: Live 起始日（spec FR-002 = 2026-04-29）。
        policy_run_id: 對應 policy run id — 寫入 log 與 episode summary.policyId。
    """

    store: LiveTrackingStore
    status_path: Path
    build_frames: FrameBuilder
    initial_nav: float
    start_anchor: date
    policy_run_id: str

    def run_once(self, today: date, *, pipeline_id: str) -> PipelineResult:
        """Execute one pipeline run — see module docstring for stages。"""
        start_ms = time.monotonic_ns() // 1_000_000

        # Stage 1: guard — refuse if previous run still flagged active
        status = LiveTrackingStatus.load(self.status_path)
        if status.is_running:
            # Caller (FastAPI handler) is responsible for the asyncio.Lock-level
            # 409；this is a defensive backstop for direct CLI invocations.
            raise RefreshInProgressError(
                f"pipeline already running (pid={status.running_pid})"
            )

        # Stage 2: mark_running + persist
        pid = os.getpid()
        started_at = datetime.now(UTC)
        status.mark_running(pid=pid, started_at=started_at)
        status.write(self.status_path)

        logger.info(
            "daily_tracker_pipeline_start pipeline_id=%s pid=%d today=%s "
            "policy_run_id=%s last_frame_date=%s",
            pipeline_id,
            pid,
            today.isoformat(),
            self.policy_run_id,
            (
                status.last_frame_date.isoformat()
                if status.last_frame_date is not None
                else "null"
            ),
        )

        try:
            # Stage 3: compute missing trading days
            missing = missing_trading_days(
                status.last_frame_date,
                today,
                start_anchor=self.start_anchor,
            )

            # Stage 4: no-op early return (FR-008)
            if not missing:
                duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
                status = LiveTrackingStatus.load(self.status_path)
                status.mark_succeeded(last_frame_date=None)
                status.write(self.status_path)
                logger.info(
                    "daily_tracker_pipeline_complete pipeline_id=%s "
                    "frames_appended=0 smc_zones_computed=0 "
                    "pipeline_duration_ms=%d final_status=noop",
                    pipeline_id,
                    duration_ms,
                )
                return PipelineResult(
                    pipeline_id=pipeline_id,
                    frames_appended=0,
                    smc_zones_computed=0,
                    pipeline_duration_ms=duration_ms,
                    final_status="noop",
                    last_frame_date=status.last_frame_date,
                )

            # Stage 5 + 6: build new frames + recompute (delegated)
            current = self.store.load()
            try:
                new_envelope = self.build_frames(
                    current_envelope=current,
                    missing_days=missing,
                    initial_nav=self.initial_nav,
                    start_anchor=self.start_anchor,
                )
            except DataFetchError as exc:
                self._fail("DATA_FETCH", exc, pipeline_id, start_ms)
                raise
            except WriteError:
                # Caller-bubbled WriteError shouldn't happen in build_frames —
                # but if it does, propagate without re-classifying.
                raise
            except Exception as exc:
                self._fail("INFERENCE", exc, pipeline_id, start_ms)
                raise InferenceError(str(exc)) from exc

            # Append-only invariant guard (INV-3) — defensive; build_frames
            # implementation MUST NOT rewrite history.
            if current is not None:
                self._verify_append_only(current, new_envelope)

            # Stage 7: atomic write
            try:
                self.store.atomic_write(new_envelope)
            except Exception as exc:
                self._fail("WRITE", exc, pipeline_id, start_ms)
                raise WriteError(str(exc)) from exc

            # Stage 8: mark_succeeded + structured log
            last_frame_date = _last_frame_date(new_envelope)
            status = LiveTrackingStatus.load(self.status_path)
            status.mark_succeeded(last_frame_date=last_frame_date)
            status.write(self.status_path)

            duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
            frames_appended = len(new_envelope.trajectoryInline) - (
                len(current.trajectoryInline) if current is not None else 0
            )
            smc_zones = sum(
                len(o.fvgs) + len(o.obs) + len(o.breaks)
                for o in new_envelope.smcOverlayByAsset.values()
            )
            logger.info(
                "daily_tracker_pipeline_complete pipeline_id=%s "
                "frames_appended=%d smc_zones_computed=%d "
                "pipeline_duration_ms=%d final_status=succeeded",
                pipeline_id,
                frames_appended,
                smc_zones,
                duration_ms,
            )
            return PipelineResult(
                pipeline_id=pipeline_id,
                frames_appended=frames_appended,
                smc_zones_computed=smc_zones,
                pipeline_duration_ms=duration_ms,
                final_status="succeeded",
                last_frame_date=last_frame_date,
            )
        except Exception:
            # _fail has already persisted status — but ensure is_running
            # is reset even for unanticipated paths.
            self._ensure_not_running()
            raise

    # ---------- Internal ----------

    def _fail(
        self,
        prefix: str,
        exc: BaseException,
        pipeline_id: str,
        start_ms: int,
    ) -> None:
        msg = f"{prefix}: {exc}"
        status = LiveTrackingStatus.load(self.status_path)
        status.mark_failed(msg)
        status.write(self.status_path)
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        logger.error(
            "daily_tracker_pipeline_complete pipeline_id=%s frames_appended=0 "
            "smc_zones_computed=0 pipeline_duration_ms=%d final_status=failed "
            "error_class=%s error_message=%s",
            pipeline_id,
            duration_ms,
            prefix.lower(),
            msg,
        )

    def _ensure_not_running(self) -> None:
        status = LiveTrackingStatus.load(self.status_path)
        if status.is_running:
            status.is_running = False
            status.running_pid = None
            status.running_started_at = None
            status.write(self.status_path)

    @staticmethod
    def _verify_append_only(
        previous: EpisodeDetail, current: EpisodeDetail
    ) -> None:
        """INV-3: 連續寫入時，新 trajectory 的前 k frame 必須與舊版完全相同。"""
        prev_frames = previous.trajectoryInline
        cur_frames = current.trajectoryInline
        if len(cur_frames) < len(prev_frames):
            raise InferenceError(
                f"append-only violation: new trajectoryInline shorter "
                f"({len(cur_frames)} < {len(prev_frames)})"
            )
        for i in range(len(prev_frames)):
            if cur_frames[i].model_dump() != prev_frames[i].model_dump():
                raise InferenceError(
                    f"append-only violation: frame {i} changed across writes"
                )


def _last_frame_date(envelope: EpisodeDetail) -> date | None:
    if not envelope.trajectoryInline:
        return None
    last_ts = envelope.trajectoryInline[-1].timestamp
    # ``timestamp`` 是 ISO 字串（009 spec）— 取前 10 字 = YYYY-MM-DD
    try:
        return date.fromisoformat(last_ts[:10])
    except ValueError:
        return None


__all__ = [
    "DailyTrackerPipeline",
    "DataFetchError",
    "FrameBuilder",
    "InferenceError",
    "PipelineResult",
    "RefreshInProgressError",
    "WriteError",
]
