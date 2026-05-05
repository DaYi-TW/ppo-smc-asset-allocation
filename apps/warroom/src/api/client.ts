/**
 * Fetch wrapper — 統一錯誤轉換、Idempotency-Key 注入。
 *
 * 範圍縮減（檔次 2-local）：
 *   - FR-013–015 [SCOPE-REDUCED]：不注入 Authorization header；不處理 401 redirect。
 *   - 後端 006 Spring Gateway 於本檔次不啟用 JWT；前端 client 直接 fetch。
 */

import type { ErrorEnvelopeDto } from './types.gen'
import { ApiError, type ApiErrorViewModel } from '@/viewmodels/error'
import { errorCodeToI18nKey, isRetryable } from './errorMap'
import { toApiError } from './envelopes'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'

export interface ApiRequestInit extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** mutating endpoint 加 idempotency key（POST /infer 等）；GET 不需要 */
  idempotencyKey?: string
  /** 預設 30 秒；SSE 用獨立 sse.ts 不走此 wrapper */
  timeoutMs?: number
}

function buildHeaders(init?: ApiRequestInit): Headers {
  const headers = new Headers(init?.headers ?? {})
  if (init?.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (init?.idempotencyKey) headers.set('Idempotency-Key', init.idempotencyKey)
  return headers
}

async function parseError(response: Response): Promise<ApiErrorViewModel> {
  let payload: Partial<ErrorEnvelopeDto> = {}
  try {
    payload = (await response.json()) as Partial<ErrorEnvelopeDto>
  } catch {
    /* 後端不是 JSON（如 nginx 502） */
  }
  const code = payload.code ?? `HTTP_${response.status}`
  const message = payload.message ?? response.statusText ?? 'Request failed'
  const traceId = payload.traceId ?? response.headers.get('x-trace-id') ?? 'unknown'
  if (payload.code) {
    return toApiError({
      code,
      message,
      httpStatus: response.status,
      traceId,
      ...(payload.details !== undefined ? { details: payload.details } : {}),
    } as ErrorEnvelopeDto)
  }
  return {
    code,
    message,
    i18nKey: errorCodeToI18nKey(code),
    httpStatus: response.status,
    traceId,
    retryable: isRetryable(code, response.status),
  }
}

function buildUrl(path: string): string {
  if (/^https?:/i.test(path)) return path
  const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}`
}

export async function apiFetch<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = buildHeaders(init)
  const controller = new AbortController()
  const timeout = init?.timeoutMs ?? 30_000
  const timer = setTimeout(() => controller.abort(), timeout)

  const fetchInit: RequestInit = {
    headers,
    signal: init?.signal ?? controller.signal,
  }
  if (init?.method) fetchInit.method = init.method
  if (init?.credentials) fetchInit.credentials = init.credentials
  if (init?.cache) fetchInit.cache = init.cache
  if (init?.mode) fetchInit.mode = init.mode
  if (init?.redirect) fetchInit.redirect = init.redirect
  if (init?.referrer) fetchInit.referrer = init.referrer
  if (init?.body !== undefined) {
    fetchInit.body = typeof init.body === 'string' ? init.body : JSON.stringify(init.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path), fetchInit)
  } catch (cause) {
    clearTimeout(timer)
    const aborted = (cause as Error)?.name === 'AbortError'
    throw new ApiError({
      code: aborted ? 'CLIENT_TIMEOUT' : 'NETWORK_ERROR',
      message: aborted ? `Request timed out after ${timeout}ms` : 'Network error',
      i18nKey: aborted ? 'errors.clientTimeout' : 'errors.networkError',
      httpStatus: 0,
      traceId: 'client',
      retryable: true,
    })
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    const viewModel = await parseError(response)
    throw new ApiError(viewModel)
  }

  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const apiBaseUrl = API_BASE_URL
