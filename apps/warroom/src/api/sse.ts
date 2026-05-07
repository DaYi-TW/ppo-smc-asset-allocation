/**
 * EventSource wrapper — 含指數退避重連、unmount cleanup、reconnect API。
 *
 * 對應 spec FR-011；後端 006 Gateway 提供 /api/v1/episodes/{id}/stream。
 */

export interface SseOptions<T> {
  /** 完整 URL 或 relative path（path 會自動 prefix VITE_API_BASE_URL） */
  url: string
  /** 接收事件 */
  onEvent: (event: T) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  /** 預設 3 次：1s, 2s, 4s 退避 */
  maxRetries?: number
  /** 自訂事件名稱；預設 message */
  eventName?: string
  /** withCredentials；檔次 2-local 不需 cookie 認證，預設 false */
  withCredentials?: boolean
}

export interface SseHandle {
  close(): void
  reconnect(): void
  /** 當前是否仍 active（未被 close） */
  isActive(): boolean
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'

function buildUrl(url: string): string {
  if (/^https?:/i.test(url)) return url
  const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL
  const suffix = url.startsWith('/') ? url : `/${url}`
  return `${base}${suffix}`
}

export function openSse<T = unknown>(opts: SseOptions<T>): SseHandle {
  const maxRetries = opts.maxRetries ?? 3
  let retries = 0
  let active = true
  let source: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function clearTimer() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function closeSource() {
    if (source) {
      source.close()
      source = null
    }
  }

  function connect() {
    if (!active) return
    closeSource()

    const init: EventSourceInit = {}
    if (opts.withCredentials) init.withCredentials = true
    source = new EventSource(buildUrl(opts.url), init)

    source.onopen = () => {
      retries = 0
      opts.onOpen?.()
    }

    const handler = (ev: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(ev.data) as T
        opts.onEvent(parsed)
      } catch {
        /* 忽略無效 payload，避免單一壞事件中斷整個串流 */
      }
    }
    if (opts.eventName) {
      source.addEventListener(opts.eventName, handler as EventListener)
    } else {
      source.onmessage = handler
    }

    source.onerror = (err) => {
      opts.onError?.(err)
      if (!active) return
      if (retries >= maxRetries) {
        closeSource()
        return
      }
      retries += 1
      const delay = 1000 * 2 ** (retries - 1)
      clearTimer()
      reconnectTimer = setTimeout(connect, delay)
    }
  }

  connect()

  return {
    close() {
      active = false
      clearTimer()
      closeSource()
    },
    reconnect() {
      retries = 0
      clearTimer()
      connect()
    },
    isActive() {
      return active
    },
  }
}
