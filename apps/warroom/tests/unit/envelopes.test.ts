import { describe, expect, it } from 'vitest'

import {
  buildSMCMarkerKind,
  toApiError,
  toEpisodeDetail,
  toEpisodeList,
  toEpisodeSummary,
  toInferResponse,
  toPolicyOption,
  toRewardSeries,
  toSMCMarkerFromFrame,
  toTrajectoryFrame,
} from '@/api/envelopes'
import type {
  EpisodeDetailEnvelopeDto,
  EpisodeListEnvelopeDto,
  EpisodeSummaryDto,
  ErrorEnvelopeDto,
  InferActionDto,
  PolicyMetadataDto,
  RewardSeriesDto,
  TrajectoryFrameDto,
} from '@/api/types.gen'

const summaryDto: EpisodeSummaryDto = {
  id: 'ep-1',
  policyId: 'p-1',
  startDate: '2024-01-02',
  endDate: '2024-12-31',
  nSteps: 252,
  initialNav: 1.0,
  finalNav: 1.42,
  cumulativeReturnPct: 42.0,
  annualizedReturnPct: 12.0,
  maxDrawdownPct: 10.0,
  sharpeRatio: 1.5,
  sortinoRatio: 2.1,
  includeSmc: true,
}

const ohlcv = { open: 100, high: 102, low: 99, close: 101, volume: 1_000_000 }

const frameDto: TrajectoryFrameDto = {
  timestamp: '2024-01-02',
  step: 0,
  weights: {
    riskOn: 0.5,
    riskOff: 0.4,
    cash: 0.1,
    perAsset: { NVDA: 0.5, GLD: 0.4, CASH: 0.1 },
  },
  nav: 1.0,
  drawdownPct: 0,
  reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
  smcSignals: {
    bos: 1,
    choch: 0,
    fvgDistancePct: 0.01,
    obTouching: false,
    obDistanceRatio: 0.3,
  },
  ohlcv,
  ohlcvByAsset: { NVDA: ohlcv, AMD: ohlcv, TSM: ohlcv, MU: ohlcv, GLD: ohlcv, TLT: ohlcv },
  action: {
    raw: [0.5, 0.4, 0.1, 0, 0, 0, 0],
    normalized: [0.5, 0.4, 0.1, 0, 0, 0, 0],
    logProb: -1.5,
    entropy: 1.2,
  },
}

describe('toEpisodeSummary', () => {
  it('translates wire schema to view model', () => {
    const vm = toEpisodeSummary(summaryDto)
    expect(vm.episodeId).toBe('ep-1')
    expect(vm.totalReturn).toBeCloseTo(0.42)
    expect(vm.maxDrawdown).toBeCloseTo(-0.1)
    expect(vm.totalSteps).toBe(252)
    expect(vm.status).toBe('completed')
  })

  it('preserves negative drawdown sign even if wire sends positive', () => {
    const vm = toEpisodeSummary({ ...summaryDto, maxDrawdownPct: 25 })
    expect(vm.maxDrawdown).toBe(-0.25)
  })
})

describe('toEpisodeList', () => {
  it('unwraps envelope items[]', () => {
    const env: EpisodeListEnvelopeDto = {
      items: [summaryDto],
      meta: { count: 1, generatedAt: '2026-05-07T00:00:00Z' },
    }
    const list = toEpisodeList(env)
    expect(list).toHaveLength(1)
    expect(list[0]?.episodeId).toBe('ep-1')
  })
})

describe('toTrajectoryFrame', () => {
  it('clones nested objects (no aliasing)', () => {
    const frame = toTrajectoryFrame(frameDto)
    expect(frame.weights.perAsset).toEqual(frameDto.weights.perAsset)
    expect(frame.weights.perAsset).not.toBe(frameDto.weights.perAsset)
    expect(frame.action.raw).not.toBe(frameDto.action.raw)
  })

  it('coerces null SMC distances to NaN', () => {
    const frame = toTrajectoryFrame({
      ...frameDto,
      smcSignals: { ...frameDto.smcSignals, fvgDistancePct: null, obDistanceRatio: null },
    })
    expect(Number.isNaN(frame.smcSignals.fvgDistancePct)).toBe(true)
    expect(Number.isNaN(frame.smcSignals.obDistanceRatio)).toBe(true)
  })
})

describe('toRewardSeries', () => {
  it('maps cumulative + byStep', () => {
    const dto: RewardSeriesDto = {
      cumulative: [
        {
          step: 1,
          cumulativeTotal: 0,
          cumulativeReturn: 0,
          cumulativeDrawdownPenalty: 0,
          cumulativeCostPenalty: 0,
        },
      ],
      byStep: [{ total: 0.01, returnComponent: 0.012, drawdownPenalty: 0, costPenalty: 0.002 }],
    }
    const series = toRewardSeries(dto)
    expect(series.cumulative).toHaveLength(1)
    expect(series.byStep[0]?.total).toBeCloseTo(0.01)
  })
})

describe('toEpisodeDetail', () => {
  const detailEnvelope: EpisodeDetailEnvelopeDto = {
    data: {
      summary: summaryDto,
      trajectoryInline: [frameDto],
      rewardBreakdown: { cumulative: [], byStep: [] },
      smcOverlayByAsset: {
        NVDA: { swings: [], zigzag: [], fvgs: [], obs: [], breaks: [] },
      },
    },
    meta: { generatedAt: '2026-05-07T00:00:00Z' },
  }

  it('flattens summary + populates inline arrays', () => {
    const vm = toEpisodeDetail(detailEnvelope)
    expect(vm.episodeId).toBe('ep-1')
    expect(vm.trajectoryInline).toHaveLength(1)
    expect(Object.keys(vm.smcOverlayByAsset ?? {})).toContain('NVDA')
  })

  it('uses summary.initialNav for config', () => {
    const vm = toEpisodeDetail(detailEnvelope)
    expect(vm.config.initialNav).toBe(1.0)
    expect(vm.config.symbols.length).toBe(6)
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
