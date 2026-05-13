/**
 * Feature 010 T038 — useLiveRefresh hook tests.
 *
 * 4 個 flows：
 *   (a) initial mount → status query 抓到 default fixture
 *   (b) refresh.mutate → mutation 進入 in-flight
 *   (c) refresh accepted → onSettled invalidate liveStatusKey；isRunning falling edge invalidate detail
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

  it('refresh.mutate returns accepted result and invalidates status query', async () => {
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

    // onSettled 只 invalidate status — detail invalidate 等 isRunning false→true→false edge
    const statusQuery = queryClient.getQueryState(liveStatusKey)
    expect(statusQuery?.isInvalidated).toBe(true)
    // detail query 還沒 mount → state undefined
    const detailQuery = queryClient.getQueryState(liveDetailKey('test_policy_live'))
    expect(detailQuery).toBeUndefined()
  })

  it('invalidates live detail on isRunning falling edge (pipeline finished)', async () => {
    // 先讓 status 回 isRunning=true，再切回 false，驗 hook 偵測到 edge 後 invalidate detail
    let nowRunning = true
    server.use(
      http.get(`${API_BASE}/api/v1/episodes/live/status`, () =>
        HttpResponse.json({
          last_updated: '2026-05-08T14:00:00Z',
          last_frame_date: '2026-05-07',
          data_lag_days: 1,
          is_running: nowRunning,
          last_error: null,
        }),
      ),
    )

    const { Wrapper, queryClient } = makeWrapper()
    // 預先塞一筆 detail cache，這樣 invalidate 後可驗到 isInvalidated=true
    queryClient.setQueryData(liveDetailKey('test_policy_live'), { stub: true })

    const { result } = renderHook(
      () => useLiveRefresh({ liveEpisodeId: 'test_policy_live' }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.status.data?.isRunning).toBe(true))

    // 模擬 pipeline 結束：後端切 false，重抓 status
    nowRunning = false
    await queryClient.invalidateQueries({ queryKey: liveStatusKey })
    await waitFor(() => expect(result.current.status.data?.isRunning).toBe(false))

    // falling edge 應該觸發 detail invalidate
    await waitFor(() => {
      const detailQuery = queryClient.getQueryState(liveDetailKey('test_policy_live'))
      expect(detailQuery?.isInvalidated).toBe(true)
    })
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
