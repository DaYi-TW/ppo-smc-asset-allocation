"""010 — Live tracking endpoints (POST /refresh + GET /status).

對應 spec 010 FR-015 / FR-016 / SC-004 與 contracts/openapi-live-tracking.yaml。

設計重點：
* 雙層並發保護：``asyncio.Lock`` 提供同 process 內 fast 409；status file
  ``is_running`` + pid + create_time 跨 process restart 仍可偵測 orphan（research §R6）。
* refresh 走 ``BackgroundTasks`` — 收到 202 後 daily pipeline 在背景跑，
  status endpoint 為唯一進度查詢通道（FR-011）。
* status 計算 ``data_lag_days = (today - last_frame_date).days``（calendar days，
  不是交易日；前端 badge 文字是「資料截至 N 天前」，使用者直觀以日曆日理解）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from live_tracking.pipeline import (
    DailyTrackerPipeline,
    FrameBuilder,
    PipelineResult,
)
from live_tracking.status import LiveTrackingStatus

from .episode_schemas import (
    LiveTrackingStatusResponse,
    RefreshAcceptedResponse,
    RefreshConflictResponse,
)

if TYPE_CHECKING:
    import asyncio

    from live_tracking.store import LiveTrackingStore

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _today_utc() -> date:
    return _now_utc().date()


def _estimate_duration_seconds(missing_days: int) -> int:
    """粗估 pipeline 執行時間（FR-016）。

    Per-day fetch+inference ≈ 1s，SMC overlay 全段重算 ≈ 2s（research §R4）。
    最少 1 秒（API contract minimum=1）。
    """
    return max(1, missing_days + 2)


def _read_status(status_path: Path) -> LiveTrackingStatus:
    # status.load 內已有 race retry；若仍 raise（檔案真的壞掉，非 race），
    # 不要讓 status endpoint 500——回 default + last_error 讓前端按鈕還能用，
    # pipeline 跑完一次就會 atomic-write 覆寫修復。
    try:
        return LiveTrackingStatus.load(status_path)
    except Exception as exc:
        logger.warning(
            "status_file_unreadable path=%s error=%s",
            status_path,
            exc,
        )
        return LiveTrackingStatus(last_error=f"status file unreadable: {exc!s}")


def _build_status_response(status: LiveTrackingStatus) -> LiveTrackingStatusResponse:
    """Serialize ``LiveTrackingStatus`` → API ``LiveTrackingStatusResponse``。

    ``data_lag_days`` = (today UTC - last_frame_date).days，含 weekend / holiday；
    前端 badge 文字是「資料截至 N 天前」，calendar days 才符合直覺（FR-027）。
    """
    last_frame_date = status.last_frame_date
    if last_frame_date is None:
        lag: int | None = None
    else:
        lag = (_today_utc() - last_frame_date).days
        if lag < 0:
            lag = 0  # clock skew safety

    return LiveTrackingStatusResponse(
        last_updated=(
            status.last_updated.isoformat() if status.last_updated is not None else None
        ),
        last_frame_date=(
            last_frame_date.isoformat() if last_frame_date is not None else None
        ),
        data_lag_days=lag,
        is_running=status.is_running,
        last_error=status.last_error,
    )


def _run_pipeline_sync(
    *,
    pipeline_id: str,
    status_path: Path,
    store: LiveTrackingStore,
    initial_nav: float,
    start_anchor: date,
    policy_run_id: str,
    frame_builder: FrameBuilder | None,
) -> PipelineResult | None:
    """Background task body：跑 ``DailyTrackerPipeline.run_once``。

    ``frame_builder is None`` 時表示尚未注入真實 fetch/inference pipeline；
    寫入 status.last_error 'INFERENCE: frame_builder not configured' 並 return。
    錯誤已由 pipeline 內部分類並寫入 status — 這裡僅做 logging。
    """
    if frame_builder is None:
        status = _read_status(status_path)
        status.mark_failed(
            "INFERENCE: frame_builder not configured (T014/T018 pending)"
        )
        status.write(status_path)
        logger.error(
            "live_pipeline_unconfigured pipeline_id=%s policy_run_id=%s",
            pipeline_id,
            policy_run_id,
        )
        return None

    pipeline = DailyTrackerPipeline(
        store=store,
        status_path=status_path,
        build_frames=frame_builder,
        initial_nav=initial_nav,
        start_anchor=start_anchor,
        policy_run_id=policy_run_id,
    )
    today = _today_utc()
    try:
        return pipeline.run_once(today, pipeline_id=pipeline_id)
    except Exception as exc:
        logger.exception(
            "live_pipeline_failed pipeline_id=%s error=%s", pipeline_id, exc
        )
        return None


def build_live_router(
    *,
    lock: asyncio.Lock,
    status_path: Path,
    store: LiveTrackingStore,
    initial_nav: float,
    start_anchor: date,
    policy_run_id: str,
    frame_builder: FrameBuilder | None = None,
) -> APIRouter:
    """Construct the live tracking router with injected dependencies.

    ``lock`` is the in-process ``asyncio.Lock`` providing fast 409 conflict;
    cross-restart durability is provided by ``status_path`` (FR-011 / SC-004).
    ``frame_builder`` is the dependency that fetches OHLCV + runs PPO inference
    + recomputes SMC overlay; when ``None`` the pipeline marks every refresh
    as failed (deferred-implementation marker).
    """
    router = APIRouter()

    @router.post("/api/v1/episodes/live/refresh")
    async def post_refresh(
        request: Request, background_tasks: BackgroundTasks
    ) -> JSONResponse:
        # In-process single-flight (research §R3): try acquire without await.
        if lock.locked():
            status = _read_status(status_path)
            running_pid = status.running_pid or 0
            running_started_at = (
                status.running_started_at.isoformat()
                if status.running_started_at is not None
                else _now_utc().isoformat()
            )
            conflict_body = RefreshConflictResponse(
                running_pid=running_pid,
                running_started_at=running_started_at,
            )
            return JSONResponse(status_code=409, content=conflict_body.model_dump())

        await lock.acquire()
        try:
            pipeline_id = str(uuid.uuid4())

            # 估 missing days 給 estimated_duration_seconds（best-effort，不擋路徑）。
            status = _read_status(status_path)
            try:
                from live_tracking.calendar import missing_trading_days

                missing = len(
                    missing_trading_days(
                        status.last_frame_date,
                        _today_utc(),
                        start_anchor=start_anchor,
                    )
                )
            except Exception:
                missing = 1

            background_tasks.add_task(
                _wrapped_pipeline_runner,
                lock=lock,
                pipeline_id=pipeline_id,
                status_path=status_path,
                store=store,
                initial_nav=initial_nav,
                start_anchor=start_anchor,
                policy_run_id=policy_run_id,
                frame_builder=frame_builder,
            )

            accepted_body = RefreshAcceptedResponse(
                accepted=True,
                pipeline_id=pipeline_id,
                estimated_duration_seconds=_estimate_duration_seconds(missing),
            )
            return JSONResponse(status_code=202, content=accepted_body.model_dump())
        except Exception:
            # 同步失敗時必須釋放 lock，否則永遠卡 409
            lock.release()
            raise

    @router.get("/api/v1/episodes/live/status")
    async def get_status() -> JSONResponse:
        status = _read_status(status_path)
        body = _build_status_response(status)
        return JSONResponse(status_code=200, content=body.model_dump())

    return router


async def _wrapped_pipeline_runner(
    *,
    lock: asyncio.Lock,
    pipeline_id: str,
    status_path: Path,
    store: LiveTrackingStore,
    initial_nav: float,
    start_anchor: date,
    policy_run_id: str,
    frame_builder: FrameBuilder | None,
) -> None:
    """Background runner that always releases the lock on completion."""
    try:
        # Pipeline is sync; run in default thread pool so we don't block the event loop.
        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: _run_pipeline_sync(
                pipeline_id=pipeline_id,
                status_path=status_path,
                store=store,
                initial_nav=initial_nav,
                start_anchor=start_anchor,
                policy_run_id=policy_run_id,
                frame_builder=frame_builder,
            ),
        )
    finally:
        if lock.locked():
            lock.release()


__all__ = ["build_live_router"]
