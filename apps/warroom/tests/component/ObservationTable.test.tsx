/**
 * ObservationTable component test — 驗證 row 數量與關鍵 cell 顯示。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ObservationTable } from '@/components/panels/ObservationTable'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const frame: TrajectoryFrame = {
  timestamp: '2024-01-02',
  step: 0,
  weights: {
    riskOn: 0.45,
    riskOff: 0.4,
    cash: 0.15,
    perAsset: { NVDA: 0.18, AMD: 0.14, TSM: 0.13, MU: 0, GLD: 0.25, TLT: 0.15, CASH: 0.15 },
  },
  nav: 100_000,
  drawdownPct: -0.01,
  reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
  smcSignals: { bos: 1, choch: 0, fvgDistancePct: 0.012, obTouching: false, obDistanceRatio: 0.34 },
  ohlcv: { open: 492, high: 495, low: 487, close: 488, volume: 34_120_000 },
  action: { raw: [0.18, 0.14, 0.13, 0, 0.25, 0.15, 0.15], normalized: [], logProb: 0, entropy: 0 },
}

describe('ObservationTable', () => {
  it('renders one row per feature', () => {
    render(<ObservationTable frame={frame} />)
    // 2 (NAV/Drawdown) + 7 perAsset + 5 SMC = 14 body + 1 header
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(15)
  })

  it('shows NVDA weight in body', () => {
    render(<ObservationTable frame={frame} />)
    expect(screen.getByText('weight.NVDA')).toBeInTheDocument()
  })

  it('renders bos value as "1"', () => {
    render(<ObservationTable frame={frame} />)
    expect(screen.getByText('smc.bos')).toBeInTheDocument()
  })
})
