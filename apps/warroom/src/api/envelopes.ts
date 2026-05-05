/**
 * DTO ↔ ViewModel 轉換 — 對應 data-model.md §11。
 *
 * 設計原則：
 *   1. 所有從外部進入的資料先過此層；UI 層只認 ViewModel。
 *   2. 失敗時 throw — 不靜默 fallback（錯誤交由 React Query / ErrorBoundary 處理）。
 *   3. 浮點不變條件（weights sum、reward total）此層不檢查（dev-only assert 在
 *      utils/invariants.ts 由呼叫端決定要不要跑）。
 */

import type {
  ActionVectorDto,
  EpisodeDetailDto,
  EpisodeSummaryDto,
  ErrorEnvelopeDto,
  InferActionDto,
  PolicyMetadataDto,
  RewardSeriesDto,
  RewardSnapshotDto,
  SMCSignalsDto,
  TrajectoryFrameDto,
  WeightAllocationDto,
} from './types.gen'
import type {
  EpisodeDetailViewModel,
  EpisodeSummaryViewModel,
} from '@/viewmodels/episode'
import type { ApiErrorViewModel } from '@/viewmodels/error'
import type { InferResponseViewModel } from '@/viewmodels/infer'
import type { PolicyOption } from '@/viewmodels/policy'
import type {
  RewardCumulativePoint,
  RewardSeries,
  RewardSnapshot,
} from '@/viewmodels/reward'
import type { SMCMarker, SMCMarkerKind, SMCSignals } from '@/viewmodels/smc'
import type {
  ActionVector,
  OHLCV,
  TrajectoryFrame,
  WeightAllocation,
} from '@/viewmodels/trajectory'
import { errorCodeToI18nKey, isRetryable } from './errorMap'

export function toEpisodeSummary(dto: EpisodeSummaryDto): EpisodeSummaryViewModel {
  return {
    episodeId: dto.episodeId,
    policyId: dto.policyId,
    policyVersion: dto.policyVersion,
    startDate: dto.startDate,
    endDate: dto.endDate,
    totalReturn: dto.totalReturn,
    maxDrawdown: dto.maxDrawdown,
    sharpeRatio: dto.sharpeRatio,
    totalSteps: dto.totalSteps,
    status: dto.status,
    createdAt: dto.createdAt,
  }
}

function toWeightAllocation(dto: WeightAllocationDto): WeightAllocation {
  return {
    riskOn: dto.riskOn,
    riskOff: dto.riskOff,
    cash: dto.cash,
    perAsset: { ...dto.perAsset },
  }
}

function toSMCSignals(dto: SMCSignalsDto): SMCSignals {
  return {
    bos: dto.bos,
    choch: dto.choch,
    fvgDistancePct: dto.fvgDistancePct,
    obTouching: dto.obTouching,
    obDistanceRatio: dto.obDistanceRatio,
  }
}

function toOHLCV(dto: { open: number; high: number; low: number; close: number; volume: number }): OHLCV {
  return { open: dto.open, high: dto.high, low: dto.low, close: dto.close, volume: dto.volume }
}

function toActionVector(dto: ActionVectorDto): ActionVector {
  return {
    raw: [...dto.raw],
    normalized: [...dto.normalized],
    logProb: dto.logProb,
    entropy: dto.entropy,
  }
}

function toRewardSnapshot(dto: RewardSnapshotDto): RewardSnapshot {
  return {
    total: dto.total,
    returnComponent: dto.returnComponent,
    drawdownPenalty: dto.drawdownPenalty,
    costPenalty: dto.costPenalty,
  }
}

export function toTrajectoryFrame(dto: TrajectoryFrameDto): TrajectoryFrame {
  return {
    timestamp: dto.timestamp,
    step: dto.step,
    weights: toWeightAllocation(dto.weights),
    nav: dto.nav,
    drawdownPct: dto.drawdownPct,
    reward: toRewardSnapshot(dto.reward),
    smcSignals: toSMCSignals(dto.smcSignals),
    ohlcv: toOHLCV(dto.ohlcv),
    action: toActionVector(dto.action),
  }
}

export function toRewardSeries(dto: RewardSeriesDto): RewardSeries {
  return {
    cumulative: dto.cumulative.map<RewardCumulativePoint>((p) => ({
      step: p.step,
      cumulativeTotal: p.cumulativeTotal,
      cumulativeReturn: p.cumulativeReturn,
      cumulativeDrawdownPenalty: p.cumulativeDrawdownPenalty,
      cumulativeCostPenalty: p.cumulativeCostPenalty,
    })),
    byStep: dto.byStep.map(toRewardSnapshot),
  }
}

export function toEpisodeDetail(dto: EpisodeDetailDto): EpisodeDetailViewModel {
  const summary = toEpisodeSummary(dto)
  const trajectoryInline = dto.trajectoryInline?.map(toTrajectoryFrame)
  const base: EpisodeDetailViewModel = {
    ...summary,
    config: {
      initialNav: dto.config.initialNav,
      symbols: [...dto.config.symbols],
      rebalanceFrequency: dto.config.rebalanceFrequency,
      transactionCostBps: dto.config.transactionCostBps,
      slippageBps: dto.config.slippageBps,
      riskFreeRate: dto.config.riskFreeRate,
    },
    rewardBreakdown: toRewardSeries(dto.rewardBreakdown),
  }
  // exactOptionalPropertyTypes: 條件式擴充，避免 undefined 進物件
  if (dto.trajectoryUri) base.trajectoryUri = dto.trajectoryUri
  if (trajectoryInline) base.trajectoryInline = trajectoryInline
  if (dto.errorMessage) base.errorMessage = dto.errorMessage
  return base
}

export function toPolicyOption(dto: PolicyMetadataDto): PolicyOption {
  return {
    policyId: dto.policyId,
    policyVersion: dto.policyVersion,
    displayName: dto.displayName,
    trainedAt: dto.trainedAt,
    trainingDataRange: { ...dto.trainingDataRange },
    configSummary: dto.configSummary,
    metrics: { ...dto.metrics },
    active: dto.active,
  }
}

export function toInferResponse(dto: InferActionDto): InferResponseViewModel {
  return {
    action: toActionVector(dto.action),
    policyId: dto.policyId,
    policyVersion: dto.policyVersion,
    inferredAt: dto.inferredAt,
    latencyMs: dto.latencyMs,
  }
}

export function toApiError(dto: ErrorEnvelopeDto): ApiErrorViewModel {
  const result: ApiErrorViewModel = {
    code: dto.code,
    message: dto.message,
    i18nKey: errorCodeToI18nKey(dto.code),
    httpStatus: dto.httpStatus,
    traceId: dto.traceId,
    retryable: isRetryable(dto.code, dto.httpStatus),
  }
  if (dto.details) result.details = dto.details
  return result
}

/** SMCMarker 從 trajectory 萃取 — 純函式，於 utils/chart-helpers.ts 也會匯出便利 wrapper。 */
export function buildSMCMarkerKind(
  bos: -1 | 0 | 1,
  choch: -1 | 0 | 1,
): SMCMarkerKind | null {
  if (bos === 1) return 'BOS_BULL'
  if (bos === -1) return 'BOS_BEAR'
  if (choch === 1) return 'CHOCH_BULL'
  if (choch === -1) return 'CHOCH_BEAR'
  return null
}

export function toSMCMarkerFromFrame(frame: TrajectoryFrame): SMCMarker | null {
  const kind = buildSMCMarkerKind(frame.smcSignals.bos, frame.smcSignals.choch)
  if (!kind) return null
  return {
    id: `${kind}-${frame.timestamp}`,
    kind,
    timestamp: frame.timestamp,
    price: frame.ohlcv.close,
    active: true,
    description: `${kind} @ ${frame.timestamp}`,
    rule: kind.startsWith('BOS') ? 'Break of Structure' : 'Change of Character',
  }
}
