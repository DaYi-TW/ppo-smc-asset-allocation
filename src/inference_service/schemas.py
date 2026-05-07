"""Pydantic schema — PredictionPayload / HealthResponse / ErrorResponse.

對應 data-model §2~§4 + contracts/openapi.yaml. 99% 對齊 ``predict.py`` 既有
JSON 輸出，僅新增 ``triggered_by`` / ``inference_id`` / ``inferred_at_utc`` 三欄.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TargetWeights(BaseModel):
    """7 維 simplex (NVDA / AMD / TSM / MU / GLD / TLT / CASH)."""

    NVDA: float = Field(ge=0.0, le=1.0)
    AMD: float = Field(ge=0.0, le=1.0)
    TSM: float = Field(ge=0.0, le=1.0)
    MU: float = Field(ge=0.0, le=1.0)
    GLD: float = Field(ge=0.0, le=1.0)
    TLT: float = Field(ge=0.0, le=1.0)
    CASH: float = Field(ge=0.0, le=1.0)


class PredictionContext(BaseModel):
    """可追溯欄位（G-I-2 / G-III-2）."""

    data_root: str
    include_smc: bool
    n_warmup_steps: int
    current_nav_at_as_of: float


class PredictionPayload(BaseModel):
    """每次 inference 完成的事件 payload.

    Contract invariant：除了 ``triggered_by`` / ``inference_id`` / ``inferred_at_utc``
    三欄外，其他欄位 byte-identical 對齊 ``predict.py`` JSON。Phase 7 contract
    test (T046) 自動驗證。
    """

    # 既有欄位（對齊 predict.py，欄位順序刻意保留）
    as_of_date: str
    next_trading_day_target: str
    policy_path: str
    deterministic: bool
    target_weights: TargetWeights
    weights_capped: bool
    renormalized: bool
    context: PredictionContext

    # 005 新增
    triggered_by: Literal["scheduled", "manual"]
    inference_id: str
    inferred_at_utc: str


class HealthResponse(BaseModel):
    """``GET /healthz`` 回應."""

    status: Literal["ok", "degraded"]
    uptime_seconds: int
    policy_loaded: bool
    redis_reachable: bool
    last_inference_at_utc: str | None = None
    next_scheduled_run_utc: str | None = None


class ErrorResponse(BaseModel):
    """統一錯誤回應 schema（FR-012 / contracts/error-codes.md）."""

    code: str
    message: str
    error_id: str
    timestamp_utc: str
