/**
 * Feature 010 T040 — LiveRefreshButton tests (FR-023 / FR-024 / FR-025).
 *
 * 4 個 flows：
 *   (a) idle → enabled，無 spinner
 *   (b) mutation isPending → disabled + spinner + 「更新中…」label
 *   (c) isPipelineRunning=true（status.is_running 推送）→ disabled
 *   (d) click → mutate 觸發；accepted 結果觸發 onResult kind='accepted'
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { describe, expect, it, vi } from 'vitest'
import type { UseMutationResult } from '@tanstack/react-query'

import { LiveRefreshButton } from '@/components/overview/LiveRefreshButton'
import i18n from '@/i18n'
import type { RefreshResult } from '@/api/episodes'

function withI18n(node: React.ReactNode) {
  return <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
}

function makeMutation(
  overrides: Partial<UseMutationResult<RefreshResult, Error, void>> = {},
  mutateImpl?: (
    _: undefined,
    options: {
      onSuccess?: (result: RefreshResult) => void
      onError?: (error: Error) => void
    },
  ) => void,
): UseMutationResult<RefreshResult, Error, void> {
  return {
    mutate: mutateImpl ?? vi.fn(),
    mutateAsync: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    isIdle: true,
    status: 'idle',
    data: undefined,
    error: null,
    failureCount: 0,
    failureReason: null,
    submittedAt: 0,
    variables: undefined,
    context: undefined,
    isPaused: false,
    ...overrides,
  } as unknown as UseMutationResult<RefreshResult, Error, void>
}

describe('LiveRefreshButton', () => {
  it('idle → enabled, no spinner', () => {
    render(withI18n(<LiveRefreshButton refresh={makeMutation()} />))
    const btn = screen.getByTestId('live-refresh-button')
    expect(btn).not.toBeDisabled()
    expect(screen.queryByTestId('live-refresh-spinner')).toBeNull()
  })

  it('mutation isPending → disabled + spinner + running label', () => {
    render(
      withI18n(
        <LiveRefreshButton refresh={makeMutation({ isPending: true })} />,
      ),
    )
    const btn = screen.getByTestId('live-refresh-button')
    expect(btn).toBeDisabled()
    expect(screen.getByTestId('live-refresh-spinner')).toBeInTheDocument()
    expect(btn.textContent).toMatch(/更新中|running/i)
  })

  it('isPipelineRunning=true → disabled even when mutation is idle', () => {
    render(
      withI18n(
        <LiveRefreshButton refresh={makeMutation()} isPipelineRunning={true} />,
      ),
    )
    expect(screen.getByTestId('live-refresh-button')).toBeDisabled()
  })

  it('click → triggers mutate; accepted result calls onResult kind=accepted', () => {
    const onResult = vi.fn()
    const mutate = vi.fn(
      (
        _: undefined,
        opts: { onSuccess?: (r: RefreshResult) => void },
      ) => {
        opts.onSuccess?.({
          status: 'accepted',
          payload: {
            accepted: true,
            pipelineId: 'pid-1',
            estimatedDurationSeconds: 8,
            pollStatusUrl: '/api/v1/episodes/live/status',
          },
        })
      },
    )
    render(
      withI18n(
        <LiveRefreshButton
          refresh={makeMutation({}, mutate)}
          onResult={onResult}
        />,
      ),
    )
    fireEvent.click(screen.getByTestId('live-refresh-button'))
    expect(mutate).toHaveBeenCalledOnce()
    expect(onResult).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'accepted' }),
    )
  })
})
