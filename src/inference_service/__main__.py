"""``python -m inference_service`` 入口 — uvicorn boot。

對應 spec FR-014：scheduler 與 HTTP server 同 process / 同 container。
"""

from __future__ import annotations

import logging
import sys


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
    import uvicorn

    from .app import create_app
    from .config import ServiceConfig
    from .handler import init_state

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

    # Phase 5 will swap this for an async redis pool from redis_io
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(cfg.redis_url, decode_responses=False)
    except Exception as exc:
        log.warning("redis client init failed (will start degraded): %s", exc)
        redis_client = None

    app = create_app(
        state=state, redis_client=redis_client, redis_key=cfg.redis_key
    )

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=cfg.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
