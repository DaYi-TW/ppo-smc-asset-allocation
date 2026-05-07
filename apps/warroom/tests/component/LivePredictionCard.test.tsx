/**
 * LivePredictionCard component test — mock useLivePrediction，驗證五個顯示狀態：
 *   loading / notReady (404) / fetch error / payload / run error。
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LivePredictionCard } from '@/components/panels/LivePredictionCard'
import type { PredictionPayload } from '@/viewmodels/prediction'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
}))

const mockUseLivePrediction = vi.fn()
vi.mock('@/hooks/useLivePrediction', () => ({
  useLivePrediction: () => mockUseLivePrediction(),
}))

const samplePayload: PredictionPayload = {
  asOfDate: '2026-05-05',
  nextTradingDayTarget: '2026-05-06',
  policyPath: 'runs/exp/final_policy.zip',
  deterministic: true,
  targetWeights: { NVDA: 0.4, GLD: 0.35, CASH: 0.25 },
  weightsCapped: false,
  renormalized: false,
  context: {
    dataRoot: 'data/raw',
    includeSmc: true,
    nWarmupSteps: 30,
    currentNavAtAsOf: 1.23,
  },
  triggeredBy: 'scheduled',
  inferenceId: 'infer-1',
  inferredAtUtc: '2026-05-05T21:30:00.000Z',
}

function makeQuery(overrides: Partial<Record<string, unknown>>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: undefined,
    ...overrides,
  }
}
function makeMutation(overrides: Partial<Record<string, unknown>>) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: undefined,
    ...overrides,
  }
}

describe('LivePredictionCard', () => {
  it('shows loading state', () => {
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({ isLoading: true }),
      run: makeMutation({}),
    })
    render(<LivePredictionCard />)
    expect(screen.getByText('app.loading')).toBeInTheDocument()
  })

  it('shows notReady when latest returns 404', () => {
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({
        isError: true,
        error: { httpStatus: 404, code: 'PREDICTION_NOT_READY' },
      }),
      run: makeMutation({}),
    })
    render(<LivePredictionCard />)
    expect(screen.getByText('livePrediction.notReady')).toBeInTheDocument()
  })

  it('shows fetch error for non-404', () => {
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({
        isError: true,
        error: { httpStatus: 503, code: 'CIRCUIT_OPEN' },
      }),
      run: makeMutation({}),
    })
    render(<LivePredictionCard />)
    expect(screen.getByText(/livePrediction\.fetchFailed/)).toBeInTheDocument()
  })

  it('renders payload fields and weights sorted desc', () => {
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({ data: samplePayload }),
      run: makeMutation({}),
    })
    render(<LivePredictionCard />)
    expect(screen.getByText(samplePayload.asOfDate)).toBeInTheDocument()
    expect(screen.getByText(samplePayload.nextTradingDayTarget)).toBeInTheDocument()
    expect(screen.getByText(samplePayload.inferredAtUtc)).toBeInTheDocument()
    // 權重應由大到小：NVDA, GLD, CASH
    const tickers = screen.getAllByText(/^(NVDA|GLD|CASH)$/).map((el) => el.textContent)
    expect(tickers).toEqual(['NVDA', 'GLD', 'CASH'])
  })

  it('clicking runNow invokes mutate', () => {
    const mutate = vi.fn()
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({ data: samplePayload }),
      run: makeMutation({ mutate }),
    })
    render(<LivePredictionCard />)
    fireEvent.click(screen.getByRole('button', { name: 'livePrediction.runNow' }))
    expect(mutate).toHaveBeenCalledTimes(1)
  })

  it('shows run error', () => {
    mockUseLivePrediction.mockReturnValue({
      latest: makeQuery({ data: samplePayload }),
      run: makeMutation({
        isError: true,
        error: { code: 'GATEWAY_TIMEOUT', httpStatus: 504 },
      }),
    })
    render(<LivePredictionCard />)
    expect(screen.getByText(/livePrediction\.runFailed/)).toBeInTheDocument()
  })
})
