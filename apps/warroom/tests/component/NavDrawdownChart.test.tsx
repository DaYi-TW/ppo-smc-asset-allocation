/**
 * NavDrawdownChart component test — 雙軸 NAV/drawdown 渲染。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { NavDrawdownChart } from '@/components/charts/NavDrawdownChart'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function makeFrame(step: number, nav: number, drawdownPct: number): TrajectoryFrame {
  return {
    timestamp: `2024-01-${String(step + 1).padStart(2, '0')}`,
    step,
    weights: {
      riskOn: 0.7,
      riskOff: 0.2,
      cash: 0.1,
      perAsset: { NVDA: 0.7, AMD: 0, TSM: 0, GLD: 0.1, TLT: 0.1, MU: 0, CASH: 0.1 },
    },
    nav,
    drawdownPct,
    reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
    smcSignals: {
      bos: 0,
      choch: 0,
      fvgDistancePct: NaN,
      obTouching: false,
      obDistanceRatio: NaN,
    },
    ohlcv: { open: 100, high: 105, low: 95, close: 102, volume: 1_000_000 },
    action: { raw: [], normalized: [], logProb: 0, entropy: 0 },
  }
}

describe('NavDrawdownChart', () => {
  it('renders figure with NAV chart aria-label', () => {
    const frames = [
      makeFrame(0, 100_000, 0),
      makeFrame(1, 102_000, 0),
      makeFrame(2, 95_000, -0.0686),
      makeFrame(3, 98_000, -0.0392),
    ]
    render(<NavDrawdownChart frames={frames} height={200} />)
    expect(screen.getByRole('figure', { name: 'overview.navChart.title' })).toBeInTheDocument()
  })

  it('does not crash with empty frames', () => {
    render(<NavDrawdownChart frames={[]} height={200} />)
    expect(screen.getByRole('figure')).toBeInTheDocument()
  })
})
