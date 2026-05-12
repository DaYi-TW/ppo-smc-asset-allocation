/**
 * Feature 010 T054 — FailureToast tests (FR-025 / SC-009).
 *
 * 對應 spec 010 FR-025 / SC-009：
 *   當 status.last_error 非 null → render persistent banner 含
 *     - 失敗時間（last_updated）
 *     - 錯誤訊息（last_error 字串）
 *     - 「再試一次」按鈕（觸發 mutation）
 *   success 後 banner 消失（last_error 變 null）
 *
 * 5 個 cases：
 *   (a) last_error=null → 不渲染 banner
 *   (b) DATA_FETCH: prefix → 渲染 banner + 顯示時間 + 顯示原始訊息
 *   (c) INFERENCE: prefix → 渲染 banner（同 a 結構）
 *   (d) WRITE: prefix → 渲染 banner（同 a 結構）
 *   (e) 點「再試一次」→ refresh.mutate 被呼叫
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { describe, expect, it, vi } from 'vitest'
import type { UseMutationResult } from '@tanstack/react-query'

import { FailureToast } from '@/components/overview/FailureToast'
import i18n from '@/i18n'
import type { RefreshResult } from '@/api/episodes'

function withI18n(node: React.ReactNode) {
  return <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
}

function makeMutation(
  overrides: Partial<UseMutationResult<RefreshResult, Error, void>> = {},
  mutateImpl?: (
    _: undefined,
    options: { onSuccess?: (r: RefreshResult) => void; onError?: (e: Error) => void },
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

describe('FailureToast', () => {
  it('does not render when lastError is null', () => {
    render(
      withI18n(
        <FailureToast
          lastError={null}
          lastUpdated={null}
          refresh={makeMutation()}
        />,
      ),
    )
    expect(screen.queryByTestId('failure-toast')).toBeNull()
  })

  it('renders banner with DATA_FETCH error and timestamp', () => {
    render(
      withI18n(
        <FailureToast
          lastError="DATA_FETCH: yfinance request timed out"
          lastUpdated="2026-05-08T03:14:00Z"
          refresh={makeMutation()}
        />,
      ),
    )
    const toast = screen.getByTestId('failure-toast')
    expect(toast).toBeInTheDocument()
    expect(toast.textContent).toContain('yfinance request timed out')
    // 時間必須出現在 banner 中（局部匹配 ISO date 部分即可）
    expect(toast.textContent).toMatch(/2026-05-08|05[-/]08/)
  })

  it('renders banner with INFERENCE error', () => {
    render(
      withI18n(
        <FailureToast
          lastError="INFERENCE: policy.predict produced NaN"
          lastUpdated="2026-05-08T03:14:00Z"
          refresh={makeMutation()}
        />,
      ),
    )
    const toast = screen.getByTestId('failure-toast')
    expect(toast).toBeInTheDocument()
    expect(toast.textContent).toContain('policy.predict produced NaN')
  })

  it('renders banner with WRITE error', () => {
    render(
      withI18n(
        <FailureToast
          lastError="WRITE: disk full"
          lastUpdated="2026-05-08T03:14:00Z"
          refresh={makeMutation()}
        />,
      ),
    )
    const toast = screen.getByTestId('failure-toast')
    expect(toast).toBeInTheDocument()
    expect(toast.textContent).toContain('disk full')
  })

  it('clicking retry button triggers refresh.mutate', () => {
    const mutate = vi.fn()
    render(
      withI18n(
        <FailureToast
          lastError="DATA_FETCH: yfinance timeout"
          lastUpdated="2026-05-08T03:14:00Z"
          refresh={makeMutation({}, mutate)}
        />,
      ),
    )
    fireEvent.click(screen.getByTestId('failure-toast-retry'))
    expect(mutate).toHaveBeenCalledOnce()
  })

  it('disables retry button while mutation isPending', () => {
    render(
      withI18n(
        <FailureToast
          lastError="DATA_FETCH: yfinance timeout"
          lastUpdated="2026-05-08T03:14:00Z"
          refresh={makeMutation({ isPending: true })}
        />,
      ),
    )
    expect(screen.getByTestId('failure-toast-retry')).toBeDisabled()
  })
})
