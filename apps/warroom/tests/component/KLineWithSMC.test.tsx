/**
 * KLineWithSMC component test — 確認 marker 數量正確（與 fixture BOS/CHoCh/OB 計數對齊）。
 *
 * 因 jsdom 不支援 canvas，全面 mock lightweight-charts；
 * 驗證重點：傳給 setMarkers() 的陣列長度 = buildSMCMarkers(frames).length
 *           （或在 visibleKinds 過濾後對應）。
 */

import { render } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { KLineWithSMC } from '@/components/charts/KLineWithSMC'
import { buildSMCMarkers } from '@/utils/chart-helpers'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const setMarkers = vi.fn()
const setData = vi.fn()
const applyOptions = vi.fn()
const remove = vi.fn()
const resize = vi.fn()
const addCandlestickSeries = vi.fn(() => ({
  setData,
  setMarkers,
  applyOptions,
}))

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Normal: 0 },
  createChart: vi.fn(() => ({
    addCandlestickSeries,
    applyOptions,
    remove,
    resize,
  })),
}))

function makeFrame(
  step: number,
  bos: -1 | 0 | 1,
  choch: -1 | 0 | 1,
  obTouching: boolean,
): TrajectoryFrame {
  return {
    timestamp: `2024-01-${String(step + 1).padStart(2, '0')}`,
    step,
    weights: {
      riskOn: 0.5,
      riskOff: 0.4,
      cash: 0.1,
      perAsset: { NVDA: 0.5, AMD: 0, TSM: 0, GLD: 0.4, TLT: 0, MU: 0, CASH: 0.1 },
    },
    nav: 100_000,
    drawdownPct: 0,
    reward: { total: 0, returnComponent: 0, drawdownPenalty: 0, costPenalty: 0 },
    smcSignals: { bos, choch, fvgDistancePct: 0.01, obTouching, obDistanceRatio: 0.1 },
    ohlcv: { open: 500, high: 510, low: 495, close: 505, volume: 1_000_000 },
    action: { raw: [], normalized: [], logProb: 0, entropy: 0 },
  }
}

describe('KLineWithSMC', () => {
  beforeEach(() => {
    setMarkers.mockClear()
    setData.mockClear()
  })

  it('forwards all SMC markers to setMarkers when visibleKinds is undefined', () => {
    const frames: TrajectoryFrame[] = [
      makeFrame(0, 1, 0, false), // BOS_BULL
      makeFrame(1, -1, 0, false), // BOS_BEAR
      makeFrame(2, 0, 1, false), // CHOCH_BULL
      makeFrame(3, 0, 0, true), // OB
    ]
    const expected = buildSMCMarkers(frames)
    render(<KLineWithSMC frames={frames} height={200} />)

    expect(setMarkers).toHaveBeenCalled()
    const lastCall = setMarkers.mock.calls.at(-1)
    expect(lastCall?.[0]).toHaveLength(expected.length)
    expect(expected).toHaveLength(4)
  })

  it('filters markers by visibleKinds', () => {
    const frames: TrajectoryFrame[] = [
      makeFrame(0, 1, 0, false), // BOS_BULL
      makeFrame(1, -1, 0, false), // BOS_BEAR
      makeFrame(2, 0, 1, false), // CHOCH_BULL
    ]
    render(
      <KLineWithSMC
        frames={frames}
        height={200}
        visibleKinds={new Set(['BOS_BULL', 'BOS_BEAR'])}
      />,
    )
    const lastCall = setMarkers.mock.calls.at(-1)
    expect(lastCall?.[0]).toHaveLength(2)
  })

  it('renders figure with i18n aria-label', () => {
    const { getByRole } = render(<KLineWithSMC frames={[]} height={200} />)
    expect(getByRole('figure', { name: 'trajectory.kline.title' })).toBeInTheDocument()
  })
})
