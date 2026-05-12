/**
 * Feature 010 T038 — useLiveRefresh hook tests.
 *
 * 4 個 flows：
 *   (a) initial mount → status query 抓到 default fixture
 *   (b) refresh.mutate → mutation 進入 in-flight
 *   (c) refresh accepted → onSettled invalidate liveStatusKey + liveDetailKey
 *   (d) refresh conflict → result.status='conflict'，hook 不丟例外
 */

import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { useLiveRefresh, liveStatusKey, liveDetailKey } from '@/hooks/useLiveRefresh'
import { server } from '@/mocks/server'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'

afterEach(() => {
  server.resetHandlers()
})

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return { Wrapper, queryClient }
}

describe('useLiveRefresh', () => {
  it('fetches initial status on mount', async () => {
    const { Wrapper } = makeWrapper()
    const { result } = renderHook(() => useLiveRefresh(), { wrapper: Wrapper })

    await waitFor(() => {
      expect(result.current.status.data).toBeDefined()
    })
    expect(result.current.status.data?.dataLagDays).toBe(1)
    expect(result.current.status.data?.isRunning).toBe(false)
  })

  it('refresh.mutate returns accepted result and invalidates queries', async () => {
    const { Wrapper, queryClient } = makeWrapper()
    const { result } = renderHook(
      () => useLiveRefresh({ liveEpisodeId: 'test_policy_live' }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.status.data).toBeDefined())

    const refreshResult = await result.current.refresh.mutateAsync()
    expect(refreshResult.status).toBe('accepted')
    if (refreshResult.status === 'accepted') {
      expect(refreshResult.payload.estimatedDurationSeconds).toBe(8)
    }

    // onSettled 觸發過 invalidate — query 會被標 stale，下一次 refetch 會跑
    const statusQuery = queryClient.getQueryState(liveStatusKey)
    const detailQuery = queryClient.getQueryState(liveDetailKey('test_policy_live'))
    expect(statusQuery?.isInvalidated).toBe(true)
    // detail query 還沒 mount → state undefined（但 invalidate 不會炸）
    expect(detailQuery === undefined || detailQuery.isInvalidated).toBe(true)
  })

  it('refresh on 409 returns conflict result without throwing', async () => {
    server.use(
      http.post(`${API_BASE}/api/v1/episodes/live/refresh`, () =>
        HttpResponse.json(
          {
            detail: 'pipeline already running',
            running_pid: 9999,
            running_started_at: '2026-05-08T14:00:01Z',
            poll_status_url: '/api/v1/episodes/live/status',
          },
          { status: 409 },
        ),
      ),
    )

    const { Wrapper } = makeWrapper()
    const { result } = renderHook(() => useLiveRefresh(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.status.data).toBeDefined())

    const refreshResult = await result.current.refresh.mutateAsync()
    expect(refreshResult.status).toBe('conflict')
    if (refreshResult.status === 'conflict') {
      expect(refreshResult.payload.runningPid).toBe(9999)
    }
  })

  it('refresh on unexpected status throws to caller', async () => {
    server.use(
      http.post(`${API_BASE}/api/v1/episodes/live/refresh`, () =>
        HttpResponse.json({ error: 'down' }, { status: 503 }),
      ),
    )

    const { Wrapper } = makeWrapper()
    const { result } = renderHook(() => useLiveRefresh(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.status.data).toBeDefined())
    await expect(result.current.refresh.mutateAsync()).rejects.toThrow(/503/)
  })
})
