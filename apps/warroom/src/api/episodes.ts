/**
 * Feature 010 — Live tracking endpoints (gateway pass-through).
 *
 * - GET  /api/v1/episodes/live/status     取 last_updated / last_frame_date / data_lag_days / is_running / last_error
 * - POST /api/v1/episodes/live/refresh    觸發 daily tracker pipeline；202 = 接受、409 = 已在跑
 *
 * 與 inference.ts 並列，獨立 module — Live tracking 與 inference 是不同 domain（feature 010 vs 005）。
 *
 * 409 設計細節：spec FR-016 要求 conflict body verbatim 透傳
 *   { detail, running_pid, running_started_at, poll_status_url }
 * 但 client.ts 的 parseError 只認 ErrorEnvelopeDto（含 code 欄位）。conflict body 沒 code，
 * 走 fallback 會被映射成 HTTP_409 + 失去細節。本檔避開 apiFetch，自己 fetch + 手動分流，
 * 保住 conflict body 給上層 hook 用於 toast 顯示 running_pid。
 */

import { apiBaseUrl } from './client'

export interface LiveTrackingStatus {
  lastUpdated: string | null
  lastFrameDate: string | null
  dataLagDays: number | null
  isRunning: boolean
  lastError: string | null
}

export interface RefreshAccepted {
  accepted: true
  pipelineId: string
  estimatedDurationSeconds: number
  pollStatusUrl: string
}

export interface RefreshConflict {
  detail: string
  runningPid: number
  runningStartedAt: string
  pollStatusUrl: string
}

/** 上層 hook 用 — 區分 202 與 409 兩條路徑 */
export type RefreshResult =
  | { status: 'accepted'; payload: RefreshAccepted }
  | { status: 'conflict'; payload: RefreshConflict }

const STATUS_TIMEOUT_MS = 5_000
const REFRESH_TIMEOUT_MS = 10_000

function buildUrl(path: string): string {
  const base = apiBaseUrl.endsWith('/') ? apiBaseUrl.slice(0, -1) : apiBaseUrl
  return `${base}${path}`
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchLiveStatus(): Promise<LiveTrackingStatus> {
  const resp = await fetchWithTimeout(
    buildUrl('/api/v1/episodes/live/status'),
    { method: 'GET', headers: { Accept: 'application/json' } },
    STATUS_TIMEOUT_MS,
  )
  if (!resp.ok) {
    throw new Error(`live/status request failed: ${resp.status} ${resp.statusText}`)
  }
  const body = (await resp.json()) as {
    last_updated: string | null
    last_frame_date: string | null
    data_lag_days: number | null
    is_running: boolean
    last_error: string | null
  }
  return {
    lastUpdated: body.last_updated,
    lastFrameDate: body.last_frame_date,
    dataLagDays: body.data_lag_days,
    isRunning: body.is_running,
    lastError: body.last_error,
  }
}

export async function triggerRefresh(): Promise<RefreshResult> {
  const resp = await fetchWithTimeout(
    buildUrl('/api/v1/episodes/live/refresh'),
    { method: 'POST', headers: { Accept: 'application/json' } },
    REFRESH_TIMEOUT_MS,
  )

  if (resp.status === 202) {
    const body = (await resp.json()) as {
      accepted: true
      pipeline_id: string
      estimated_duration_seconds: number
      poll_status_url: string
    }
    return {
      status: 'accepted',
      payload: {
        accepted: body.accepted,
        pipelineId: body.pipeline_id,
        estimatedDurationSeconds: body.estimated_duration_seconds,
        pollStatusUrl: body.poll_status_url,
      },
    }
  }

  if (resp.status === 409) {
    const body = (await resp.json()) as {
      detail: string
      running_pid: number
      running_started_at: string
      poll_status_url: string
    }
    return {
      status: 'conflict',
      payload: {
        detail: body.detail,
        runningPid: body.running_pid,
        runningStartedAt: body.running_started_at,
        pollStatusUrl: body.poll_status_url,
      },
    }
  }

  throw new Error(
    `live/refresh unexpected status ${resp.status}: ${resp.statusText}`,
  )
}
