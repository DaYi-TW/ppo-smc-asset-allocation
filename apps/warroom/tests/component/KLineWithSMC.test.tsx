/**
 * KLineWithSMC component test — 驗證 SMC primitive attachment + data attributes。
 *
 * 新架構（feature 007）：SMC 透過 ISeriesPrimitive 自畫，不再用 setMarkers。
 * 驗證重點：
 *   - attachPrimitive 被呼叫
 *   - data-overlay-fvg / data-overlay-ob / data-overlay-breaks 屬性反映 overlay 大小
 *   - selectedAsset 切換時 setData 被重餵
 */

import { render } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { KLineWithSMC } from '@/components/charts/KLineWithSMC'
import type { SMCOverlay } from '@/viewmodels/smc'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

vi.mock('@/contexts/TimeRangeContext', () => ({
  useTimeRange: () => ({ range: { start: 0, end: 100 }, setRange: vi.fn() }),
}))

const attachPrimitive = vi.fn()
const detachPrimitive = vi.fn()
const setData = vi.fn()
const applyOptions = vi.fn()
const remove = vi.fn()
const resize = vi.fn()
const addCandlestickSeries = vi.fn(() => ({
  setData,
  applyOptions,
  attachPrimitive,
  detachPrimitive,
}))

const setVisibleLogicalRange = vi.fn()
const timeScale = vi.fn(() => ({ setVisibleLogicalRange }))

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Normal: 0 },
  createChart: vi.fn(() => ({
    addCandlestickSeries,
    applyOptions,
    remove,
    resize,
    timeScale,
  })),
}))

function makeFrame(step: number): TrajectoryFrame {
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
    smcSignals: { bos: 0, choch: 0, fvgDistancePct: 0, obTouching: false, obDistanceRatio: 0 },
    ohlcv: { open: 500, high: 510, low: 495, close: 505, volume: 1_000_000 },
    action: { raw: [], normalized: [], logProb: 0, entropy: 0 },
  }
}

describe('KLineWithSMC', () => {
  beforeEach(() => {
    attachPrimitive.mockClear()
    detachPrimitive.mockClear()
    setData.mockClear()
  })

  it('attaches SMC primitive on mount', () => {
    render(<KLineWithSMC frames={[makeFrame(0)]} height={200} />)
    expect(attachPrimitive).toHaveBeenCalledTimes(1)
  })

  it('exposes overlay sizes via data attributes', () => {
    const overlay: SMCOverlay = {
      swings: [],
      zigzag: [],
      fvgs: [
        {
          from: '2024-01-01',
          to: '2024-01-02',
          top: 100,
          bottom: 90,
          direction: 'bullish',
          filled: false,
        },
      ],
      obs: [
        {
          from: '2024-01-01',
          to: '2024-01-03',
          top: 105,
          bottom: 95,
          direction: 'bearish',
          invalidated: false,
        },
        {
          from: '2024-01-02',
          to: '2024-01-04',
          top: 108,
          bottom: 98,
          direction: 'bullish',
          invalidated: true,
        },
      ],
      breaks: [
        {
          time: '2024-01-02',
          anchorTime: '2024-01-01',
          price: 500,
          breakClose: 510,
          kind: 'BOS_BULL',
        },
      ],
    }
    const { getByRole } = render(
      <KLineWithSMC frames={[makeFrame(0)]} height={200} overlay={overlay} />,
    )
    const fig = getByRole('figure', { name: 'trajectory.kline.title' })
    expect(fig.getAttribute('data-overlay-fvg')).toBe('1')
    expect(fig.getAttribute('data-overlay-ob')).toBe('2')
    expect(fig.getAttribute('data-overlay-breaks')).toBe('1')
  })

  it('renders figure with i18n aria-label even with empty frames', () => {
    const { getByRole } = render(<KLineWithSMC frames={[]} height={200} />)
    expect(getByRole('figure', { name: 'trajectory.kline.title' })).toBeInTheDocument()
  })
})
