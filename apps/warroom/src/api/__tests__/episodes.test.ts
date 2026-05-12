/**
 * Feature 010 T037 — episodes.ts API client unit tests.
 *
 * 三個 flows：
 *   (a) fetchLiveStatus 正常 200 → camelCase 轉換正確
 *   (b) triggerRefresh 202 → status='accepted' + 對應欄位
 *   (c) triggerRefresh 409 → status='conflict' + verbatim 透傳
 *       （critical：FR-016，conflict body 不能在 client.ts 的 parseError 被吞掉）
 */

import { afterEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'

import { fetchLiveStatus, triggerRefresh } from '@/api/episodes'
import { server } from '@/mocks/server'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'

afterEach(() => {
  server.resetHandlers()
})

describe('fetchLiveStatus', () => {
  it('parses snake_case response into camelCase view model', async () => {
    const status = await fetchLiveStatus()
    expect(status).toEqual({
      lastUpdated: '2026-05-08T14:00:00Z',
      lastFrameDate: '2026-05-07',
      dataLagDays: 1,
      isRunning: false,
      lastError: null,
    })
  })

  it('preserves null fields (initial state)', async () => {
    server.use(
      http.get(`${API_BASE}/api/v1/episodes/live/status`, () =>
        HttpResponse.json({
          last_updated: null,
          last_frame_date: null,
          data_lag_days: null,
          is_running: false,
          last_error: null,
        }),
      ),
    )
    const status = await fetchLiveStatus()
    expect(status.dataLagDays).toBeNull()
    expect(status.lastFrameDate).toBeNull()
  })
})

describe('triggerRefresh', () => {
  it('returns accepted result on 202', async () => {
    const result = await triggerRefresh()
    expect(result.status).toBe('accepted')
    if (result.status === 'accepted') {
      expect(result.payload.accepted).toBe(true)
      expect(result.payload.pipelineId).toBe(
        '550e8400-e29b-41d4-a716-446655440000',
      )
      expect(result.payload.estimatedDurationSeconds).toBe(8)
      expect(result.payload.pollStatusUrl).toBe('/api/v1/episodes/live/status')
    }
  })

  it('returns conflict result on 409 with running_pid pass-through', async () => {
    // FR-016 critical: 409 body verbatim — 含 running_pid / running_started_at
    server.use(
      http.post(`${API_BASE}/api/v1/episodes/live/refresh`, () =>
        HttpResponse.json(
          {
            detail: 'pipeline already running',
            running_pid: 12345,
            running_started_at: '2026-05-08T14:00:01Z',
            poll_status_url: '/api/v1/episodes/live/status',
          },
          { status: 409 },
        ),
      ),
    )

    const result = await triggerRefresh()
    expect(result.status).toBe('conflict')
    if (result.status === 'conflict') {
      expect(result.payload.detail).toBe('pipeline already running')
      expect(result.payload.runningPid).toBe(12345)
      expect(result.payload.runningStartedAt).toBe('2026-05-08T14:00:01Z')
      expect(result.payload.pollStatusUrl).toBe('/api/v1/episodes/live/status')
    }
  })

  it('throws on unexpected status code (e.g. 503)', async () => {
    server.use(
      http.post(`${API_BASE}/api/v1/episodes/live/refresh`, () =>
        HttpResponse.json({ error: 'service down' }, { status: 503 }),
      ),
    )
    await expect(triggerRefresh()).rejects.toThrow(/unexpected status 503/)
  })
})
