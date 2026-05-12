"""``python -m inference_service`` 入口 — uvicorn boot。

對應 spec FR-014：scheduler 與 HTTP server 同 process / 同 container。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """啟動 inference service（uvicorn + FastAPI + APScheduler）。

    流程：
        1. ``ServiceConfig()`` 從 env var 載入並驗證一次（startup-fail-fast）。
        2. ``init_state(cfg)`` eager-load PPO policy + env factory。
        3. 建立 redis async client（Phase 5 由 ``redis_io.create_client`` 實作；
           現階段直接用 ``redis.asyncio.from_url``）。
        4. ``create_app(state, redis_client)`` → ``uvicorn.run``。

    APScheduler 啟動由 Phase 4（T028~T031）填入 lifespan startup。
    """
    import os

    import uvicorn

    from live_tracking.frame_builder import LiveFrameBuilder
    from live_tracking.status import LiveTrackingStatus
    from live_tracking.store import LiveTrackingStore

    from .app import create_app
    from .config import ServiceConfig
    from .episodes import EpisodeStore, MultiSourceEpisodeStore
    from .handler import init_state
    from .redis_io import RedisIO
    from .scheduler import init_scheduler

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    log = logging.getLogger("inference_service")

    try:
        cfg = ServiceConfig()  # type: ignore[call-arg]
    except Exception as exc:
        log.error("config validation failed: %s", exc)
        return 2

    log.info(
        "starting inference service: policy=%s data=%s redis=%s",
        cfg.policy_path,
        cfg.data_root,
        cfg.redis_url,
    )

    state = init_state(cfg)

    # 009 — fail-fast：缺檔 / schema 錯，整個服務不啟動。
    try:
        episode_store = EpisodeStore.from_file(cfg.episode_artefact_path)
    except FileNotFoundError as exc:
        log.error("episode artefact missing: %s", exc)
        return 3
    except Exception as exc:
        log.error("episode artefact validation failed: %s", exc)
        return 4

    redis_io: RedisIO | None
    try:
        import redis.asyncio as aioredis

        raw_client = aioredis.from_url(cfg.redis_url, decode_responses=False)
        redis_io = RedisIO(
            client=raw_client,
            channel=cfg.redis_channel,
            key=cfg.redis_key,
            ttl_seconds=cfg.redis_ttl_seconds,
        )
    except Exception as exc:
        log.warning("redis client init failed (will start degraded): %s", exc)
        redis_io = None

    # 010 — Live tracking 雙源 store + orphan recovery (FR-011 / R6)
    live_status_path: Path | None = None
    multi_store: MultiSourceEpisodeStore | None = None
    live_frame_builder: LiveFrameBuilder | None = None
    if cfg.live_policy_run_id:
        cfg.live_artefact_dir.mkdir(parents=True, exist_ok=True)
        live_artefact_path = cfg.live_artefact_dir / "live_tracking.json"
        live_status_path = cfg.live_artefact_dir / "live_tracking_status.json"
        live_store = LiveTrackingStore(live_artefact_path)
        # Orphan recovery — 先前 process 若被 SIGKILL，is_running=True 會殘留。
        if live_status_path.exists():
            status = LiveTrackingStatus.load(live_status_path)
            recovered = status.recover_orphan(current_pid=os.getpid())
            if recovered:
                status.write(live_status_path)
            log.info(
                "live_tracking_status_recovered_orphan: %s policy_run_id=%s",
                recovered,
                cfg.live_policy_run_id,
            )
        multi_store = MultiSourceEpisodeStore(oos=episode_store, live=live_store)
        # T018 — 注入真實 FrameBuilder（取代 sentinel）
        live_frame_builder = LiveFrameBuilder(
            policy_path=cfg.policy_path,
            data_root=cfg.data_root,
            policy_run_id=cfg.live_policy_run_id,
            include_smc=cfg.include_smc,
            seed=cfg.seed,
        )

    app = create_app(
        state=state,
        redis_client=redis_io,
        redis_key=cfg.redis_key,
        episode_store=multi_store if multi_store is not None else episode_store,
        live_status_path=live_status_path,
        live_start_anchor=cfg.live_start_date,
        live_initial_nav=cfg.live_initial_nav,
        live_policy_run_id=cfg.live_policy_run_id,
        live_frame_builder=live_frame_builder,
    )

    # Scheduler 與 FastAPI 同 event loop（uvicorn 啟動 lifespan 後 add startup hook）
    @app.on_event("startup")
    async def _start_scheduler() -> None:
        publisher = redis_io.publish_prediction if redis_io is not None else None
        scheduler = init_scheduler(
            state=state,
            cron_expr=cfg.schedule_cron,
            timezone_name=cfg.schedule_timezone,
            redis_publisher=publisher,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        next_run = scheduler.get_jobs()[0].next_run_time
        app.state.next_scheduled_run_utc = (
            next_run.isoformat() if next_run is not None else None
        )
        log.info("scheduler started; next run at %s", app.state.next_scheduled_run_utc)

    @app.on_event("shutdown")
    async def _stop_scheduler() -> None:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=cfg.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
