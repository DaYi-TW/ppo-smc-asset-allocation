/* eslint-disable */
/**
 * API DTO 型別 — 對齊 005 inference_service / 006 gateway 實際 wire format。
 *
 * 對應 src/inference_service/episode_schemas.py（Pydantic strict model）
 * 與 specs/009-episode-detail-store/data-model.md。
 *
 * 命名規則：<EndpointGroup><DtoName>Dto。
 *
 * Wire 格式與 ViewModel 不同（mapper envelopes.ts 處理轉換）：
 *   id ↔ episodeId, finalNav/initialNav ↔ totalReturn,
 *   maxDrawdownPct ↔ maxDrawdown, nSteps ↔ totalSteps，等等。
 */

/* ========== Episode ========== */
export interface EpisodeSummaryDto {
  id: string
  policyId: string
  startDate: string
  endDate: string
  nSteps: number
  initialNav: number
  finalNav: number
  cumulativeReturnPct: number
  annualizedReturnPct: number
  maxDrawdownPct: number
  sharpeRatio: number
  sortinoRatio: number
  includeSmc: boolean
}

export interface EpisodeListEnvelopeDto {
  items: EpisodeSummaryDto[]
  meta: {
    count: number
    generatedAt: string
  }
}

export interface OHLCVDto {
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface SMCSignalsDto {
  bos: -1 | 0 | 1
  choch: -1 | 0 | 1
  fvgDistancePct: number | null
  obTouching: boolean
  obDistanceRatio: number | null
}

export interface ActionVectorDto {
  raw: number[]
  normalized: number[]
  logProb: number
  entropy: number
}

export interface RewardSnapshotDto {
  total: number
  returnComponent: number
  drawdownPenalty: number
  costPenalty: number
}

export interface WeightAllocationDto {
  riskOn: number
  riskOff: number
  cash: number
  perAsset: Record<string, number>
}

export interface TrajectoryFrameDto {
  timestamp: string
  step: number
  weights: WeightAllocationDto
  nav: number
  drawdownPct: number
  reward: RewardSnapshotDto
  smcSignals: SMCSignalsDto
  ohlcv: OHLCVDto
  ohlcvByAsset: Record<string, OHLCVDto>
  action: ActionVectorDto
}

export interface RewardCumulativePointDto {
  step: number
  cumulativeTotal: number
  cumulativeReturn: number
  cumulativeDrawdownPenalty: number
  cumulativeCostPenalty: number
}

export interface RewardSeriesDto {
  cumulative: RewardCumulativePointDto[]
  byStep: RewardSnapshotDto[]
}

export interface SwingPointDto {
  time: string
  price: number
  kind: 'high' | 'low'
  barIndex: number
}

export interface FVGZoneDto {
  from: string
  to: string
  top: number
  bottom: number
  direction: 'bullish' | 'bearish'
  filled: boolean
}

export interface OBZoneDto {
  from: string
  to: string
  top: number
  bottom: number
  direction: 'bullish' | 'bearish'
  invalidated: boolean
}

export interface StructureBreakDto {
  time: string
  anchorTime: string
  price: number
  breakClose: number
  kind: 'BOS_BULL' | 'BOS_BEAR' | 'CHOCH_BULL' | 'CHOCH_BEAR'
}

export interface SMCOverlayDto {
  swings: SwingPointDto[]
  zigzag: SwingPointDto[]
  fvgs: FVGZoneDto[]
  obs: OBZoneDto[]
  breaks: StructureBreakDto[]
}

export interface EpisodeDetailDto {
  summary: EpisodeSummaryDto
  trajectoryInline: TrajectoryFrameDto[]
  rewardBreakdown: RewardSeriesDto
  smcOverlayByAsset: Record<string, SMCOverlayDto>
}

export interface EpisodeDetailEnvelopeDto {
  data: EpisodeDetailDto
  meta: {
    generatedAt: string
    evaluatorVersion?: string | null
    policyChecksum?: string | null
    dataChecksum?: string | null
  }
}

/* ========== Policy ========== */
export interface PolicyMetricsDto {
  sharpeRatio: number
  maxDrawdown: number
  cumulativeReturn: number
}

export interface PolicyMetadataDto {
  policyId: string
  policyVersion: string
  displayName: string
  trainedAt: string
  trainingDataRange: { start: string; end: string }
  configSummary: string
  metrics: PolicyMetricsDto
  active: boolean
}

/* ========== Inference ========== */
export interface InferRequestDto {
  policyId: string
  policyVersion?: string
  observation: number[]
}

export interface InferActionDto {
  action: ActionVectorDto
  policyId: string
  policyVersion: string
  inferredAt: string
  latencyMs: number
}

/* ========== Error envelope ========== */
export interface ErrorEnvelopeDto {
  code: string
  message: string
  httpStatus: number
  traceId: string
  details?: Record<string, unknown>
}

/* ========== SSE event payload ========== */
export type EpisodeStreamEventDto =
  | { type: 'progress'; episodeId: string; step: number; totalSteps: number; nav: number }
  | { type: 'completed'; episodeId: string; finalNav: number }
  | { type: 'error'; episodeId: string; code: string; message: string }
