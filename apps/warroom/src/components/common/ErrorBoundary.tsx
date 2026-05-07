/**
 * Top-level error boundary — 攔截 React render-time 例外，避免整頁白畫面。
 *
 * 使用方式：包在 `<App />` 外層，或包在每個路由 outlet 內。
 * 不處理 async error；那由 React Query 的 onError + ErrorEnvelope 對應 i18n 處理。
 *
 * 若 error 物件帶有 `traceId`（例如 ApiErrorViewModel）則顯示複製按鈕。
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

export interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: (error: Error, reset: () => void) => ReactNode
  onError?: (error: Error, info: ErrorInfo) => void
}

interface State {
  error: Error | null
  copied: boolean
}

function extractTraceId(error: Error): string | undefined {
  const candidate = (error as unknown as { traceId?: unknown }).traceId
  return typeof candidate === 'string' && candidate.length > 0 ? candidate : undefined
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  override state: State = { error: null, copied: false }

  static getDerivedStateFromError(error: Error): State {
    return { error, copied: false }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info)
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.error('[ErrorBoundary]', error, info)
    }
  }

  reset = (): void => {
    this.setState({ error: null, copied: false })
  }

  copyTraceId = async (traceId: string): Promise<void> => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(traceId)
      }
      this.setState({ copied: true })
    } catch {
      // ignore clipboard failures
    }
  }

  override render(): ReactNode {
    const { error, copied } = this.state
    if (error) {
      if (this.props.fallback) return this.props.fallback(error, this.reset)
      const traceId = extractTraceId(error)
      return (
        <div
          role="alert"
          className="flex flex-col items-start gap-md p-lg rounded-md bg-bg-surface text-text-primary border border-default"
        >
          <p className="font-semibold">{error.name || 'Error'}</p>
          <p className="text-sm text-text-secondary">{error.message}</p>
          {traceId ? (
            <div className="flex items-center gap-sm text-xs text-text-muted">
              <span>traceId: <code>{traceId}</code></span>
              <button
                type="button"
                onClick={() => void this.copyTraceId(traceId)}
                className="px-sm py-1 rounded-sm border border-default hover:bg-bg-elevated"
                aria-label="copy trace id"
              >
                {copied ? '✓' : '📋'}
              </button>
            </div>
          ) : null}
          <button
            type="button"
            onClick={this.reset}
            className="px-md py-sm rounded-sm bg-primary text-white hover:bg-primary-hover"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
