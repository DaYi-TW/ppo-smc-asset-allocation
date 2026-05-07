/**
 * DTO ↔ ViewModel 轉換 — 對應 data-model.md §11。
 *
 * 設計原則：
 *   1. 所有從外部進入的資料先過此層；UI 層只認 ViewModel。
 *   2. 失敗時 throw — 不靜默 fallback（錯誤交由 React Query / ErrorBoundary 處理）。
 *   3. 浮點不變條件（weights sum、reward total）此層不檢查（dev-only assert 在
 *      utils/invariants.ts 由呼叫端決定要不要跑）。
 *   4. 005/006 wire format 用 id/finalNav/maxDrawdownPct/nSteps，viewmodel 沿用
 *      原命名（episodeId/totalReturn/maxDrawdown/totalSteps）— 此層做欄位翻譯。
 */

import type {
  ActionVectorDto,
  EpisodeDetailDto,
  EpisodeDetailEnvelopeDto,
  EpisodeListEnvelopeDto,
  EpisodeSummaryDto,
  ErrorEnvelopeDto,
  FVGZoneDto,
  InferActionDto,
  OBZoneDto,
  PolicyMetadataDto,
  RewardSeriesDto,
  RewardSnapshotDto,
  SMCOverlayDto,
  SMCSignalsDto,
  StructureBreakDto,
  SwingPointDto,
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
import type {
  FVGZone,
  OBZone,
  SMCMarker,
  SMCMarkerKind,
  SMCOverlay,
  SMCSignals,
  StructureBreak,
  SwingPoint,
} from '@/viewmodels/smc'
import type {
  ActionVector,
  OHLCV,
  TrajectoryFrame,
  WeightAllocation,
} from '@/viewmodels/trajectory'
import { errorCodeToI18nKey, isRetryable } from './errorMap'

export function toEpisodeSummary(dto: EpisodeSummaryDto): EpisodeSummaryViewModel {
  return {
    episodeId: dto.id,
    policyId: dto.policyId,
    policyVersion: 'v1',
    startDate: dto.startDate,
    endDate: dto.endDate,
    totalReturn: dto.cumulativeReturnPct / 100,
    maxDrawdown: -Math.abs(dto.maxDrawdownPct) / 100,
    sharpeRatio: dto.sharpeRatio,
    totalSteps: dto.nSteps,
    status: 'completed',
    createdAt: dto.endDate,
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
    fvgDistancePct: dto.fvgDistancePct ?? Number.NaN,
    obTouching: dto.obTouching,
    obDistanceRatio: dto.obDistanceRatio ?? Number.NaN,
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
  const ohlcvByAsset = Object.fromEntries(
    Object.entries(dto.ohlcvByAsset).map(([k, v]) => [k, toOHLCV(v)]),
  )
  return {
    timestamp: dto.timestamp,
    step: dto.step,
    weights: toWeightAllocation(dto.weights),
    nav: dto.nav,
    drawdownPct: dto.drawdownPct,
    reward: toRewardSnapshot(dto.reward),
    smcSignals: toSMCSignals(dto.smcSignals),
    ohlcv: toOHLCV(dto.ohlcv),
    ohlcvByAsset,
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

function toSwingPoint(dto: SwingPointDto): SwingPoint {
  return { time: dto.time, price: dto.price, kind: dto.kind, barIndex: dto.barIndex }
}

function toFVGZone(dto: FVGZoneDto): FVGZone {
  return {
    from: dto.from,
    to: dto.to,
    top: dto.top,
    bottom: dto.bottom,
    direction: dto.direction,
    filled: dto.filled,
  }
}

function toOBZone(dto: OBZoneDto): OBZone {
  return {
    from: dto.from,
    to: dto.to,
    top: dto.top,
    bottom: dto.bottom,
    direction: dto.direction,
    invalidated: dto.invalidated,
  }
}

function toStructureBreak(dto: StructureBreakDto): StructureBreak {
  return {
    time: dto.time,
    anchorTime: dto.anchorTime,
    price: dto.price,
    breakClose: dto.breakClose,
    kind: dto.kind,
  }
}

export function toSMCOverlay(dto: SMCOverlayDto): SMCOverlay {
  return {
    swings: dto.swings.map(toSwingPoint),
    zigzag: dto.zigzag.map(toSwingPoint),
    fvgs: dto.fvgs.map(toFVGZone),
    obs: dto.obs.map(toOBZone),
    breaks: dto.breaks.map(toStructureBreak),
  }
}

export function toEpisodeList(envelope: EpisodeListEnvelopeDto): EpisodeSummaryViewModel[] {
  return envelope.items.map(toEpisodeSummary)
}

const _DEFAULT_SYMBOLS = ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT'] as const

export function toEpisodeDetail(envelope: EpisodeDetailEnvelopeDto): EpisodeDetailViewModel {
  const detail: EpisodeDetailDto = envelope.data
  const summary = toEpisodeSummary(detail.summary)
  const trajectoryInline = detail.trajectoryInline.map(toTrajectoryFrame)
  const smcOverlayByAsset = Object.fromEntries(
    Object.entries(detail.smcOverlayByAsset).map(([k, v]) => [k, toSMCOverlay(v)]),
  )
  const base: EpisodeDetailViewModel = {
    ...summary,
    config: {
      initialNav: detail.summary.initialNav,
      symbols: [..._DEFAULT_SYMBOLS],
      rebalanceFrequency: 'daily',
      transactionCostBps: 0,
      slippageBps: 0,
      riskFreeRate: 0,
    },
    rewardBreakdown: toRewardSeries(detail.rewardBreakdown),
    trajectoryInline,
    smcOverlayByAsset,
  }
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
