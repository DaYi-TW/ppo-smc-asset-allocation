/* eslint-disable */
/**
 * API DTO 型別 — 由 openapi-typescript 從 006 Gateway openapi.yaml 自動產生。
 *
 * **不要手動編輯此檔**，請執行：
 *   npm run gen:openapi  # 待 006 spec 完成後啟用
 *
 * 目前為 hand-written stub，待 006 完成後以 codegen 結果取代。
 * 命名規則：<EndpointGroup><DtoName>Dto，與 data-model.md §11 對應。
 */

/* ========== Episode ========== */
export interface EpisodeSummaryDto {
  episodeId: string
  policyId: string
  policyVersion: string
  startDate: string
  endDate: string
  totalReturn: number
  maxDrawdown: number
  sharpeRatio: number
  totalSteps: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  createdAt: string
}

export interface EpisodeConfigDto {
  initialNav: number
  symbols: string[]
  rebalanceFrequency: 'daily' | 'weekly'
  transactionCostBps: number
  slippageBps: number
  riskFreeRate: number
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
  fvgDistancePct: number
  obTouching: boolean
  obDistanceRatio: number
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
  ohlcvByAsset?: Record<string, OHLCVDto>
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

export interface EpisodeDetailDto extends EpisodeSummaryDto {
  config: EpisodeConfigDto
  trajectoryUri?: string
  trajectoryInline?: TrajectoryFrameDto[]
  rewardBreakdown: RewardSeriesDto
  errorMessage?: string
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
