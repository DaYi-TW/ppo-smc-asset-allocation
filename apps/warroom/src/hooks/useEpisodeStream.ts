/**
 * useEpisodeStream — 訂閱 GET /api/v1/episodes/{id}/stream（SSE）。
 *
 * 對應 spec FR-011：live progress events。提供 status/lastEvent/reconnect。
 */

import { useEffect, useRef, useState } from 'react'

import { openSse, type SseHandle } from '@/api/sse'
import type { EpisodeStreamEventDto } from '@/api/types.gen'

export type SseStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

export interface EpisodeStreamState {
  status: SseStatus
  lastEvent: EpisodeStreamEventDto | null
  events: EpisodeStreamEventDto[]
  reconnect: () => void
  close: () => void
}

export function useEpisodeStream(
  episodeId: string | undefined,
  enabled: boolean = true,
): EpisodeStreamState {
  const [status, setStatus] = useState<SseStatus>('idle')
  const [lastEvent, setLastEvent] = useState<EpisodeStreamEventDto | null>(null)
  const [events, setEvents] = useState<EpisodeStreamEventDto[]>([])
  const handleRef = useRef<SseHandle | null>(null)

  useEffect(() => {
    if (!enabled || !episodeId) {
      setStatus('idle')
      return
    }
    setStatus('connecting')
    const handle = openSse<EpisodeStreamEventDto>({
      url: `/api/v1/episodes/${encodeURIComponent(episodeId)}/stream`,
      onOpen: () => setStatus('open'),
      onEvent: (ev) => {
        setLastEvent(ev)
        setEvents((prev) => [...prev, ev])
      },
      onError: () => setStatus('error'),
    })
    handleRef.current = handle
    return () => {
      handle.close()
      handleRef.current = null
      setStatus('closed')
    }
  }, [episodeId, enabled])

  return {
    status,
    lastEvent,
    events,
    reconnect: () => handleRef.current?.reconnect(),
    close: () => handleRef.current?.close(),
  }
}
