/**
 * DecisionNarration component test — 驗證 i18n template 插值。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DecisionNarration } from '@/components/panels/DecisionNarration'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

// 使用真實 t 函式做模板插值；這裡 mock 一個會做 {{...}} 替換的 stub。
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      if (k === 'decision.narration.template' && opts) {
        return `Date=${opts['date']} Action=${opts['action']} Why=${opts['rationale']}`
      }
      return k
    },
  }),
}))

function makeFrame(overrides: Partial<TrajectoryFrame> = {}): TrajectoryFrame {
  return {
    timestamp: '2024-03-15',
    step: 50,
    weights: {
      riskOn: 0.7,
      riskOff: 0.2,
      cash: 0.1,
      perAsset: { NVDA: 0.45, AMD: 0.15, TSM: 0.10, MU: 0, GLD: 0.10, TLT: 0.10, CASH: 0.10 },
    },
    nav: 110_000,
    drawdownPct: -0.02,
    reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
    smcSignals: { bos: 1, choch: 0, fvgDistancePct: 0.005, obTouching: true, obDistanceRatio: 0 },
    ohlcv: { open: 100, high: 105, low: 99, close: 104, volume: 1_000_000 },
    action: { raw: [], normalized: [], logProb: 0, entropy: 0 },
    ...overrides,
  }
}

describe('DecisionNarration', () => {
  it('picks NVDA as top asset and includes BOS rationale', () => {
    render(<DecisionNarration frame={makeFrame()} />)
    const text = screen.getByText(/Date=/).textContent ?? ''
    expect(text).toContain('NVDA')
    expect(text).toContain('BOS↑')
    expect(text).toContain('OB-touch')
  })

  it('includes MDD note when drawdown exceeds -5%', () => {
    render(
      <DecisionNarration
        frame={makeFrame({
          drawdownPct: -0.12,
          smcSignals: { bos: 0, choch: 0, fvgDistancePct: NaN, obTouching: false, obDistanceRatio: NaN },
        })}
      />,
    )
    const text = screen.getByText(/Date=/).textContent ?? ''
    expect(text).toMatch(/MDD/)
  })
})
