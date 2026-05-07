"""FastAPI app factory + 4 endpoints。

對應 spec FR-001 / FR-008 / FR-009 + contracts/openapi.yaml。Phase 3 T022~T025 實作。
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .handler import InferenceState, run_inference
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
) -> FastAPI:
    """Construct FastAPI app with eager-loaded state + redis client.

    Args:
        state: InferenceState built at lifespan startup（``init_state`` 的回傳值）.
        redis_client: ``redis.asyncio.Redis``（or fake for tests）。``None`` for
            unit tests that don't exercise the cache path.
        redis_key: Redis key holding the latest snapshot（contracts default）.
    """
    app = FastAPI(
        title="PPO Inference Service",
        version="2.0.0",
        description="C-lite 路線：FastAPI + APScheduler + Redis pub/sub。",
    )
    app.state.inference_state = state
    app.state.redis_client = redis_client
    app.state.redis_key = redis_key

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

    return app
