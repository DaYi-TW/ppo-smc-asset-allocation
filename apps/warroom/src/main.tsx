/**
 * Entry point — i18n init、MSW（dev only）、React Query Provider、router。
 *
 * MSW 啟用條件：VITE_USE_MOCK === 'true'（本檔次 2-local 預設 true）。
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import ReactDOM from 'react-dom/client'

import { App } from './App'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { startWebVitals } from './utils/webVitals'
import './i18n'
import './styles/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error: unknown) => {
        // 自訂判定 retryable 已於 ApiError 內處理；預設失敗 1 次後放棄
        if (failureCount >= 1) return false
        const retryable =
          typeof error === 'object' && error !== null && 'viewModel' in error
            ? (error as { viewModel: { retryable: boolean } }).viewModel.retryable
            : false
        return retryable
      },
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

async function enableMockingIfNeeded(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCK !== 'true') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'warn' })
}

startWebVitals()

void enableMockingIfNeeded().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ErrorBoundary>
    </React.StrictMode>,
  )
})
