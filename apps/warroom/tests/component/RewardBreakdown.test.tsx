/**
 * RewardBreakdown component test — 確認雙圖（stacked bar + cumulative line）渲染。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RewardBreakdown } from '@/components/charts/RewardBreakdown'
import type { RewardSeries } from '@/viewmodels/reward'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const series: RewardSeries = {
  byStep: [
    { total: 0.001, returnComponent: 0.0014, drawdownPenalty: 0.0001, costPenalty: 0.0002 },
    { total: 0.0023, returnComponent: 0.003, drawdownPenalty: 0.0002, costPenalty: 0.0005 },
  ],
  cumulative: [
    {
      step: 0,
      cumulativeTotal: 0.001,
      cumulativeReturn: 0.0014,
      cumulativeDrawdownPenalty: 0.0001,
      cumulativeCostPenalty: 0.0002,
    },
    {
      step: 1,
      cumulativeTotal: 0.0033,
      cumulativeReturn: 0.0044,
      cumulativeDrawdownPenalty: 0.0003,
      cumulativeCostPenalty: 0.0007,
    },
  ],
}

describe('RewardBreakdown', () => {
  it('renders figure with reward title', () => {
    render(<RewardBreakdown series={series} />)
    expect(screen.getByRole('figure', { name: 'decision.reward.title' })).toBeInTheDocument()
  })

  it('handles step prop within range', () => {
    const { container } = render(<RewardBreakdown series={series} step={0} height={150} />)
    expect(container.querySelectorAll('.recharts-responsive-container').length).toBe(2)
  })
})
