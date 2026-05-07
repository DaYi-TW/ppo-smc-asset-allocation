import { describe, expect, it } from 'vitest'

import {
  buildSMCMarkers,
  buildWeightStackPoints,
  clamp,
  computeDrawdownSeries,
  findFrameIndex,
} from '@/utils/chart-helpers'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

function makeFrame(overrides: Partial<TrajectoryFrame> = {}): TrajectoryFrame {
  return {
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
      bos: 0,
      choch: 0,
      fvgDistancePct: 0.01,
      obTouching: false,
      obDistanceRatio: 0.3,
    },
    ohlcv: { open: 100, high: 102, low: 99, close: 101, volume: 1_000_000 },
    action: { raw: [0.5, 0.4, 0.1], normalized: [0.5, 0.4, 0.1], logProb: -1.5, entropy: 1.2 },
    ...overrides,
  }
}

describe('clamp', () => {
  it('clamps values into the range', () => {
    expect(clamp(5, 0, 10)).toBe(5)
    expect(clamp(-1, 0, 10)).toBe(0)
    expect(clamp(99, 0, 10)).toBe(10)
  })

  it('returns min for NaN', () => {
    expect(clamp(NaN, 0, 10)).toBe(0)
  })
})

describe('computeDrawdownSeries', () => {
  it('tracks high-water mark and drawdown%', () => {
    const series = computeDrawdownSeries([
      { timestamp: 'd1', nav: 100 },
      { timestamp: 'd2', nav: 120 },
      { timestamp: 'd3', nav: 90 },
      { timestamp: 'd4', nav: 110 },
    ])
    expect(series[0]?.highWaterMark).toBe(100)
    expect(series[1]?.highWaterMark).toBe(120)
    expect(series[2]?.drawdownPct).toBeCloseTo(-0.25, 5)
    expect(series[3]?.highWaterMark).toBe(120)
  })
})

describe('buildSMCMarkers', () => {
  it('emits BOS bull marker', () => {
    const markers = buildSMCMarkers([
      makeFrame({ smcSignals: { ...makeFrame().smcSignals, bos: 1 } }),
    ])
    expect(markers).toHaveLength(1)
    expect(markers[0]?.kind).toBe('BOS_BULL')
  })

  it('emits OB marker when obTouching=true', () => {
    const markers = buildSMCMarkers([
      makeFrame({ smcSignals: { ...makeFrame().smcSignals, obTouching: true } }),
    ])
    expect(markers).toHaveLength(1)
    expect(markers[0]?.kind).toBe('OB')
    expect(markers[0]?.rangeStart?.price).toBe(99)
    expect(markers[0]?.rangeEnd?.price).toBe(102)
  })

  it('emits no markers for flat signals', () => {
    expect(buildSMCMarkers([makeFrame()])).toHaveLength(0)
  })

  it('emits BOS + CHoCh independently in same frame', () => {
    const markers = buildSMCMarkers([
      makeFrame({ smcSignals: { ...makeFrame().smcSignals, bos: 1, choch: -1 } }),
    ])
    expect(markers.map((m) => m.kind).sort()).toEqual(['BOS_BULL', 'CHOCH_BEAR'])
  })
})

describe('buildWeightStackPoints', () => {
  it('flattens weights and per-asset', () => {
    const points = buildWeightStackPoints([makeFrame()])
    expect(points[0]?.cash).toBe(0.1)
    expect(points[0]?.['NVDA']).toBe(0.5)
  })
})

describe('findFrameIndex', () => {
  it('finds exact match', () => {
    const frames = [{ timestamp: 'a' }, { timestamp: 'b' }, { timestamp: 'c' }]
    expect(findFrameIndex(frames, 'b')).toBe(1)
  })

  it('returns lower-bound on miss', () => {
    const frames = [{ timestamp: 'a' }, { timestamp: 'c' }, { timestamp: 'e' }]
    expect(findFrameIndex(frames, 'b')).toBe(1)
    expect(findFrameIndex(frames, 'd')).toBe(2)
  })
})
