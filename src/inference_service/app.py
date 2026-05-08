"""FastAPI app factory + 4 endpoints。

對應 spec FR-001 / FR-008 / FR-009 + contracts/openapi.yaml。Phase 3 T022~T025 實作。
010：``episode_store`` 接受 ``EpisodeStore``（OOS 單源，向後相容）或
``MultiSourceEpisodeStore``（OOS + Live 雙源）。當提供 multi-source 時，
``/api/v1/episodes/live/*`` 兩個新 endpoint 自動掛載。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .episodes import EpisodeStore, MultiSourceEpisodeStore
from .handler import InferenceState, run_inference
from .live_endpoints import build_live_router
from .redis_io import RedisIO
from .schemas import ErrorResponse, HealthResponse, PredictionPayload

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _error_response(
    *, status_code: int, code: str, message: str
) -> JSONResponse:
    """Build a contracts/error-codes.md-compliant ErrorResponse."""
    body = ErrorResponse(
        code=code,
        message=message,
        error_id=str(uuid.uuid4()),
        timestamp_utc=_now_iso(),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def create_app(
    *,
    state: InferenceState,
    redis_client: Any | None,
    redis_key: str = "predictions:latest",
    episode_store: EpisodeStore | MultiSourceEpisodeStore | None = None,
    live_status_path: Path | None = None,
    live_start_anchor: date | None = None,
    live_initial_nav: float = 1.0,
    live_policy_run_id: str = "",
) -> FastAPI:
    """Construct FastAPI app with eager-loaded state + redis client + episode store.

    Args:
        state: InferenceState built at lifespan startup（``init_state`` 的回傳值）.
        redis_client: ``redis.asyncio.Redis``（or fake for tests）。``None`` for
            unit tests that don't exercise the cache path.
        redis_key: Redis key holding the latest snapshot（contracts default）.
        episode_store: 009 — eager-loaded OOS ``episode_detail.json``，或 010
            ``MultiSourceEpisodeStore``（OOS + Live 雙源）。``None`` 時
            ``GET /api/v1/episodes*`` 回 503（degraded）。
        live_status_path: 010 — ``live_tracking_status.json`` 路徑。當
            ``episode_store`` 為 ``MultiSourceEpisodeStore`` 且此值非 ``None``
            時，掛載 ``POST /api/v1/episodes/live/refresh`` +
            ``GET /api/v1/episodes/live/status``。
        live_start_anchor: 010 — Live tracking 起始日（FR-002，預設 spec
            2026-04-29）。
        live_initial_nav: 010 — Live 起始 NAV（承接 OOS 終值）。
        live_policy_run_id: 010 — Live tracking 對應的 policy run id（用於 log）。
    """
    app = FastAPI(
        title="PPO Inference Service",
        version="2.0.0",
        description="C-lite 路線：FastAPI + APScheduler + Redis pub/sub。",
    )
    app.state.inference_state = state
    app.state.redis_client = redis_client
    app.state.redis_key = redis_key
    app.state.episode_store = episode_store

    @app.post("/infer/run")
    async def post_infer_run(request: Request) -> JSONResponse:
        st: InferenceState = request.app.state.inference_state
        try:
            payload = await run_inference(st, "manual")
        except Exception:
            err_id = str(uuid.uuid4())
            traceback.print_exc(file=sys.stderr)
            logger.error("inference_failed error_id=%s", err_id)
            return _error_response(
                status_code=500,
                code="INFERENCE_FAILED",
                message=(
                    "Inference handler raised an internal error. "
                    "See stderr stack trace via error_id."
                ),
            )

        # publish 失敗不影響 200 回應（FR-011 解耦）
        client = request.app.state.redis_client
        if isinstance(client, RedisIO):
            try:
                await client.publish_prediction(payload)
            except Exception:
                traceback.print_exc(file=sys.stderr)
                logger.warning("redis_publish_failed inference_id=%s", payload.inference_id)

        return JSONResponse(status_code=200, content=payload.model_dump())

    @app.get("/infer/latest")
    async def get_infer_latest(request: Request) -> JSONResponse:
        client = request.app.state.redis_client
        key = request.app.state.redis_key
        if client is None:
            return _error_response(
                status_code=503,
                code="REDIS_UNREACHABLE",
                message="Redis client not configured.",
            )

        # Two paths：RedisIO（production / Phase 5 wired）vs raw client（unit test stub）
        if isinstance(client, RedisIO):
            try:
                payload = await client.get_latest()
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return _error_response(
                    status_code=503,
                    code="REDIS_UNREACHABLE",
                    message="Redis GET failed; cache temporarily unreachable.",
                )
            if payload is None:
                return _error_response(
                    status_code=404,
                    code="NO_PREDICTION_YET",
                    message=(
                        "No prediction in cache yet. Trigger /infer/run or wait "
                        "for the next scheduled run."
                    ),
                )
            return JSONResponse(status_code=200, content=payload.model_dump())

        try:
            raw = await client.get(key)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return _error_response(
                status_code=503,
                code="REDIS_UNREACHABLE",
                message="Redis GET failed; cache temporarily unreachable.",
            )
        if raw is None:
            return _error_response(
                status_code=404,
                code="NO_PREDICTION_YET",
                message=(
                    "No prediction in cache yet. Trigger /infer/run or wait "
                    "for the next scheduled run."
                ),
            )
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
            payload = PredictionPayload.model_validate(data)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return _error_response(
                status_code=500,
                code="INFERENCE_FAILED",
                message="Cached payload is malformed.",
            )
        return JSONResponse(status_code=200, content=payload.model_dump())

    @app.get("/healthz")
    async def healthz(request: Request) -> JSONResponse:
        st: InferenceState = request.app.state.inference_state
        client = request.app.state.redis_client

        policy_loaded = st.policy is not None
        redis_reachable = False
        if isinstance(client, RedisIO):
            redis_reachable = await client.ping()
        elif client is not None:
            try:
                await client.ping()
                redis_reachable = True
            except Exception:
                redis_reachable = False

        uptime_seconds = int(
            (datetime.now(UTC) - st.started_at_utc).total_seconds()
        )

        status_value = "ok" if (policy_loaded and redis_reachable) else "degraded"
        http_status = 200 if status_value == "ok" else 503

        body = HealthResponse(
            status=status_value,  # type: ignore[arg-type]
            uptime_seconds=uptime_seconds,
            policy_loaded=policy_loaded,
            redis_reachable=redis_reachable,
            last_inference_at_utc=(
                st.last_inference_at_utc.isoformat()
                if st.last_inference_at_utc is not None
                else None
            ),
            next_scheduled_run_utc=getattr(
                request.app.state, "next_scheduled_run_utc", None
            ),
        )
        return JSONResponse(status_code=http_status, content=body.model_dump())

    @app.get("/api/v1/episodes")
    async def get_episodes(request: Request) -> JSONResponse:
        store = request.app.state.episode_store
        if store is None:
            return _error_response(
                status_code=503,
                code="EPISODE_STORE_UNAVAILABLE",
                message="Episode artefact not loaded.",
            )
        envelope = store.list_envelope()
        return JSONResponse(
            status_code=200,
            content=envelope.model_dump(mode="json", by_alias=True),
        )

    @app.get("/api/v1/episodes/{episode_id}")
    async def get_episode_detail(episode_id: str, request: Request) -> JSONResponse:
        store = request.app.state.episode_store
        if store is None:
            return _error_response(
                status_code=503,
                code="EPISODE_STORE_UNAVAILABLE",
                message="Episode artefact not loaded.",
            )
        envelope = store.get_envelope(episode_id)
        if envelope is None:
            return _error_response(
                status_code=404,
                code="EPISODE_NOT_FOUND",
                message=f"Episode '{episode_id}' not found.",
            )
        return JSONResponse(
            status_code=200,
            content=envelope.model_dump(mode="json", by_alias=True),
        )

    # ---------- 010 Live tracking endpoints (FR-015 / FR-016) ----------
    if (
        isinstance(episode_store, MultiSourceEpisodeStore)
        and episode_store.live is not None
        and live_status_path is not None
    ):
        anchor = live_start_anchor or date(2026, 4, 29)
        lock = asyncio.Lock()
        app.state.live_refresh_lock = lock
        live_router = build_live_router(
            lock=lock,
            status_path=live_status_path,
            store=episode_store.live,
            initial_nav=live_initial_nav,
            start_anchor=anchor,
            policy_run_id=live_policy_run_id,
        )
        app.include_router(live_router)

    return app
