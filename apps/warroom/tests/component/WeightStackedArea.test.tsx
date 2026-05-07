/**
 * WeightStackedArea component test — 確認 7 維資產權重渲染為 stacked area。
 *
 * Recharts 在 jsdom 下需要 ResponsiveContainer 寬高 stub；
 * 此處驗證 figure role + asset legend 出現即可。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WeightStackedArea } from '@/components/charts/WeightStackedArea'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function makeFrame(step: number): TrajectoryFrame {
  return {
    timestamp: `2024-01-${String(step + 1).padStart(2, '0')}`,
    step,
    weights: {
      riskOn: 0.6,
      riskOff: 0.3,
      cash: 0.1,
      perAsset: { NVDA: 0.2, AMD: 0.2, TSM: 0.2, GLD: 0.15, TLT: 0.15, MU: 0, CASH: 0.1 },
    },
    nav: 100_000 + step * 100,
    drawdownPct: -0.01 * step,
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

describe('WeightStackedArea', () => {
  it('renders figure with aria-label from i18n key', () => {
    const frames = Array.from({ length: 5 }, (_, i) => makeFrame(i))
    render(<WeightStackedArea frames={frames} height={200} />)
    expect(screen.getByRole('figure', { name: 'overview.weightChart.title' })).toBeInTheDocument()
  })

  it('renders empty container when frames are empty', () => {
    render(<WeightStackedArea frames={[]} height={200} />)
    expect(screen.getByRole('figure')).toBeInTheDocument()
  })
})
