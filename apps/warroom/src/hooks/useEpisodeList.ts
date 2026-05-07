/**
 * useEpisodeList — GET /api/v1/episodes
 *
 * 005/006 不接受 query params（MVP 僅 1 個 OOS episode），filters 保留 API
 * 以維持呼叫端相容；本層直接拉全 list 後在前端 narrow（OverviewPage 取
 * status='completed' 的 latest）。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { toEpisodeList } from '@/api/envelopes'
import { episodeKeys } from '@/api/queryKeys'
import type { EpisodeListEnvelopeDto } from '@/api/types.gen'
import type { EpisodeSummaryViewModel } from '@/viewmodels/episode'
import type { ApiErrorViewModel } from '@/viewmodels/error'

export interface EpisodeListFilters {
  policyId?: string
  status?: 'pending' | 'running' | 'completed' | 'failed'
  from?: string
  to?: string
  page?: number
  pageSize?: number
}

export function useEpisodeList(
  filters: EpisodeListFilters = {},
): UseQueryResult<EpisodeSummaryViewModel[], ApiErrorViewModel> {
  return useQuery<EpisodeSummaryViewModel[], ApiErrorViewModel>({
    queryKey: episodeKeys.list(filters as Record<string, unknown>),
    queryFn: async ({ signal }) => {
      const envelope = await apiFetch<EpisodeListEnvelopeDto>('/api/v1/episodes', { signal })
      return toEpisodeList(envelope)
    },
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  })
}
