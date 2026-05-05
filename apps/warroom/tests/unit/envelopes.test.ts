import { describe, expect, it } from 'vitest'

import {
  buildSMCMarkerKind,
  toApiError,
  toEpisodeDetail,
  toEpisodeSummary,
  toInferResponse,
  toPolicyOption,
  toRewardSeries,
  toSMCMarkerFromFrame,
  toTrajectoryFrame,
} from '@/api/envelopes'
import type {
  EpisodeDetailDto,
  EpisodeSummaryDto,
  ErrorEnvelopeDto,
  InferActionDto,
  PolicyMetadataDto,
  RewardSeriesDto,
  TrajectoryFrameDto,
} from '@/api/types.gen'

const summaryDto: EpisodeSummaryDto = {
  episodeId: 'ep-1',
  policyId: 'p-1',
  policyVersion: 'v1',
  startDate: '2024-01-02',
  endDate: '2024-12-31',
  totalReturn: 0.42,
  maxDrawdown: -0.1,
  sharpeRatio: 1.5,
  totalSteps: 252,
  status: 'completed',
  createdAt: '2026-04-15T10:00:00Z',
}

const frameDto: TrajectoryFrameDto = {
  timestamp: '2024-01-02',
  step: 0,
  weights: {
    riskOn: 0.5,
    riskOff: 0.4,
    cash: 0.1,
    perAsset: { NVDA: 0.5, GLD: 0.4, CASH: 0.1 },
  },
  nav: 100000,
  drawdownPct: 0,
  reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
  smcSignals: {
    bos: 1,
    choch: 0,
    fvgDistancePct: 0.01,
    obTouching: false,
    obDistanceRatio: 0.3,
  },
  ohlcv: { open: 100, high: 102, low: 99, close: 101, volume: 1_000_000 },
  action: { raw: [0.5, 0.4, 0.1], normalized: [0.5, 0.4, 0.1], logProb: -1.5, entropy: 1.2 },
}

describe('toEpisodeSummary', () => {
  it('passes fields through', () => {
    expect(toEpisodeSummary(summaryDto)).toEqual(summaryDto)
  })
})

describe('toTrajectoryFrame', () => {
  it('clones nested objects (no aliasing)', () => {
    const frame = toTrajectoryFrame(frameDto)
    expect(frame.weights.perAsset).toEqual(frameDto.weights.perAsset)
    expect(frame.weights.perAsset).not.toBe(frameDto.weights.perAsset)
    expect(frame.action.raw).not.toBe(frameDto.action.raw)
  })
})

describe('toRewardSeries', () => {
  it('maps cumulative + byStep', () => {
    const dto: RewardSeriesDto = {
      cumulative: [
        {
          step: 0,
          cumulativeTotal: 0,
          cumulativeReturn: 0,
          cumulativeDrawdownPenalty: 0,
          cumulativeCostPenalty: 0,
        },
      ],
      byStep: [{ total: 0.01, returnComponent: 0.012, drawdownPenalty: 0, costPenalty: -0.002 }],
    }
    const series = toRewardSeries(dto)
    expect(series.cumulative).toHaveLength(1)
    expect(series.byStep[0]?.total).toBeCloseTo(0.01)
  })
})

describe('toEpisodeDetail', () => {
  const detailDto: EpisodeDetailDto = {
    ...summaryDto,
    config: {
      initialNav: 100000,
      symbols: ['NVDA', 'GLD', 'CASH'],
      rebalanceFrequency: 'daily',
      transactionCostBps: 5,
      slippageBps: 2,
      riskFreeRate: 0.045,
    },
    trajectoryInline: [frameDto],
    rewardBreakdown: { cumulative: [], byStep: [] },
  }

  it('omits undefined optional fields', () => {
    const vm = toEpisodeDetail(detailDto)
    expect('errorMessage' in vm).toBe(false)
    expect('trajectoryUri' in vm).toBe(false)
    expect(vm.trajectoryInline).toHaveLength(1)
  })

  it('includes errorMessage when present', () => {
    const vm = toEpisodeDetail({ ...detailDto, errorMessage: 'boom' })
    expect(vm.errorMessage).toBe('boom')
  })
})

describe('toPolicyOption', () => {
  it('clones nested objects', () => {
    const dto: PolicyMetadataDto = {
      policyId: 'p',
      policyVersion: 'v',
      displayName: 'P',
      trainedAt: '2026-01-01T00:00:00Z',
      trainingDataRange: { start: '2018-01-02', end: '2024-12-31' },
      configSummary: 'x',
      metrics: { sharpeRatio: 1, maxDrawdown: -0.1, cumulativeReturn: 1 },
      active: true,
    }
    const vm = toPolicyOption(dto)
    expect(vm.trainingDataRange).not.toBe(dto.trainingDataRange)
    expect(vm.metrics).not.toBe(dto.metrics)
  })
})

describe('toInferResponse', () => {
  it('passes basic fields through', () => {
    const dto: InferActionDto = {
      action: { raw: [0.5, 0.5], normalized: [0.5, 0.5], logProb: -1, entropy: 0.7 },
      policyId: 'p',
      policyVersion: 'v',
      inferredAt: '2026-04-29T12:00:00Z',
      latencyMs: 25,
    }
    const vm = toInferResponse(dto)
    expect(vm.policyId).toBe('p')
    expect(vm.action.raw).toEqual([0.5, 0.5])
  })
})

describe('toApiError', () => {
  it('attaches i18nKey + retryable flag', () => {
    const dto: ErrorEnvelopeDto = {
      code: 'POLICY_NOT_FOUND',
      message: 'not found',
      httpStatus: 404,
      traceId: 't-1',
    }
    const vm = toApiError(dto)
    expect(vm.i18nKey).toBe('errors.policyNotFound')
    expect(vm.retryable).toBe(false)
  })

  it('omits details when undefined', () => {
    const vm = toApiError({
      code: 'X',
      message: 'm',
      httpStatus: 500,
      traceId: 't',
    })
    expect('details' in vm).toBe(false)
  })

  it('preserves details when present', () => {
    const vm = toApiError({
      code: 'X',
      message: 'm',
      httpStatus: 500,
      traceId: 't',
      details: { foo: 'bar' },
    })
    expect(vm.details).toEqual({ foo: 'bar' })
  })
})

describe('buildSMCMarkerKind', () => {
  it('maps BOS bull/bear', () => {
    expect(buildSMCMarkerKind(1, 0)).toBe('BOS_BULL')
    expect(buildSMCMarkerKind(-1, 0)).toBe('BOS_BEAR')
  })

  it('maps CHoCh bull/bear when bos is 0', () => {
    expect(buildSMCMarkerKind(0, 1)).toBe('CHOCH_BULL')
    expect(buildSMCMarkerKind(0, -1)).toBe('CHOCH_BEAR')
  })

  it('returns null when both are 0', () => {
    expect(buildSMCMarkerKind(0, 0)).toBeNull()
  })

  it('prefers BOS over CHoCh', () => {
    expect(buildSMCMarkerKind(1, 1)).toBe('BOS_BULL')
  })
})

describe('toSMCMarkerFromFrame', () => {
  it('builds a marker for non-zero bos/choch', () => {
    const marker = toSMCMarkerFromFrame(toTrajectoryFrame(frameDto))
    expect(marker?.kind).toBe('BOS_BULL')
    expect(marker?.price).toBeCloseTo(101)
  })

  it('returns null when both signals are 0', () => {
    const flat = {
      ...frameDto,
      smcSignals: { ...frameDto.smcSignals, bos: 0 as const, choch: 0 as const },
    }
    expect(toSMCMarkerFromFrame(toTrajectoryFrame(flat))).toBeNull()
  })
})
