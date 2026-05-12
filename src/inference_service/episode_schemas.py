"""Episode schemas — feature 009.

對應 ``specs/009-episode-detail-store/contracts/openapi-episodes.yaml`` 與
``data-model.md``。所有 model 設 ``extra='forbid'``，防止前後端 schema 漂移
（FR-019 / Principle V）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EpisodeSummary(_StrictModel):
    id: str
    policyId: str
    startDate: str  # YYYY-MM-DD
    endDate: str
    nSteps: int = Field(ge=1)
    initialNav: float
    finalNav: float
    cumulativeReturnPct: float
    annualizedReturnPct: float
    maxDrawdownPct: NonNegativeFloat
    sharpeRatio: float
    sortinoRatio: float
    includeSmc: bool


class WeightAllocation(_StrictModel):
    riskOn: float
    riskOff: float
    cash: float
    perAsset: dict[str, float]


class RewardSnapshot(_StrictModel):
    total: float
    returnComponent: float
    drawdownPenalty: NonNegativeFloat
    costPenalty: NonNegativeFloat


class RewardCumulativePoint(_StrictModel):
    step: int = Field(ge=1)
    cumulativeTotal: float
    cumulativeReturn: float
    cumulativeDrawdownPenalty: NonNegativeFloat
    cumulativeCostPenalty: NonNegativeFloat


class RewardSeries(_StrictModel):
    byStep: list[RewardSnapshot]
    cumulative: list[RewardCumulativePoint]


class SMCSignals(_StrictModel):
    bos: Literal[-1, 0, 1]
    choch: Literal[-1, 0, 1]
    fvgDistancePct: float | None
    obTouching: bool
    obDistanceRatio: float | None


class OHLCV(_StrictModel):
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: NonNegativeFloat


class ActionVector(_StrictModel):
    raw: list[float] = Field(min_length=7, max_length=7)
    normalized: list[float] = Field(min_length=7, max_length=7)
    logProb: float
    entropy: float


class TrajectoryFrame(_StrictModel):
    timestamp: str
    step: int = Field(ge=0)
    weights: WeightAllocation
    nav: float
    drawdownPct: NonNegativeFloat
    reward: RewardSnapshot
    smcSignals: SMCSignals
    ohlcv: OHLCV
    ohlcvByAsset: dict[str, OHLCV]
    action: ActionVector


class SwingPoint(_StrictModel):
    time: str
    price: float
    kind: Literal["high", "low"]
    barIndex: int = Field(ge=0)


class FVGZone(_StrictModel):
    fvg_from: str = Field(alias="from")
    to: str
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"]
    filled: bool

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OBZone(_StrictModel):
    ob_from: str = Field(alias="from")
    to: str
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"]
    invalidated: bool

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StructureBreak(_StrictModel):
    time: str
    anchorTime: str
    price: float
    breakClose: float
    kind: Literal["BOS_BULL", "BOS_BEAR", "CHOCH_BULL", "CHOCH_BEAR"]


class SMCOverlay(_StrictModel):
    swings: list[SwingPoint]
    zigzag: list[SwingPoint]
    fvgs: list[FVGZone]
    obs: list[OBZone]
    breaks: list[StructureBreak]


class EpisodeDetail(_StrictModel):
    summary: EpisodeSummary
    trajectoryInline: list[TrajectoryFrame]
    rewardBreakdown: RewardSeries
    smcOverlayByAsset: dict[str, SMCOverlay]


class ListMeta(_StrictModel):
    count: int = Field(ge=0)
    generatedAt: str  # ISO datetime UTC


class DetailMeta(_StrictModel):
    generatedAt: str
    evaluatorVersion: str | None = None
    policyChecksum: str | None = None
    dataChecksum: str | None = None


class EpisodeListEnvelope(_StrictModel):
    items: list[EpisodeSummary]
    meta: ListMeta


class EpisodeDetailEnvelope(_StrictModel):
    data: EpisodeDetail
    meta: DetailMeta


# ---------- 010 Live Tracking response models (FR-015 / FR-016) ----------


class LiveTrackingStatusResponse(_StrictModel):
    """``GET /api/v1/episodes/live/status`` 回應 body — spec 010 FR-015。"""

    last_updated: str | None
    last_frame_date: str | None
    data_lag_days: int | None = Field(default=None, ge=0)
    is_running: bool
    last_error: str | None


class RefreshAcceptedResponse(_StrictModel):
    """``POST /api/v1/episodes/live/refresh`` 202 body — spec 010 FR-016."""

    accepted: Literal[True]
    pipeline_id: str
    estimated_duration_seconds: int = Field(ge=1)
    poll_status_url: Literal["/api/v1/episodes/live/status"] = (
        "/api/v1/episodes/live/status"
    )


class RefreshConflictResponse(_StrictModel):
    """``POST /api/v1/episodes/live/refresh`` 409 body — spec 010 SC-004."""

    detail: Literal["pipeline already running"] = "pipeline already running"
    running_pid: int
    running_started_at: str
    poll_status_url: Literal["/api/v1/episodes/live/status"] = (
        "/api/v1/episodes/live/status"
    )


__all__ = [
    "OHLCV",
    "ActionVector",
    "DetailMeta",
    "EpisodeDetail",
    "EpisodeDetailEnvelope",
    "EpisodeListEnvelope",
    "EpisodeSummary",
    "FVGZone",
    "ListMeta",
    "LiveTrackingStatusResponse",
    "OBZone",
    "RefreshAcceptedResponse",
    "RefreshConflictResponse",
    "RewardCumulativePoint",
    "RewardSeries",
    "RewardSnapshot",
    "SMCOverlay",
    "SMCSignals",
    "StructureBreak",
    "SwingPoint",
    "TrajectoryFrame",
    "WeightAllocation",
]
