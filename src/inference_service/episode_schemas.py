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


__all__ = [
    "ActionVector",
    "DetailMeta",
    "EpisodeDetail",
    "EpisodeDetailEnvelope",
    "EpisodeListEnvelope",
    "EpisodeSummary",
    "FVGZone",
    "ListMeta",
    "OBZone",
    "OHLCV",
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
