/**
 * useEpisodeList — GET /api/v1/episodes?...
 *
 * filters 為可選，傳遞為 query string；空物件 → 全部。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { toEpisodeSummary } from '@/api/envelopes'
import { episodeKeys } from '@/api/queryKeys'
import type { EpisodeSummaryDto } from '@/api/types.gen'
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

interface EpisodeListEnvelope {
  items: EpisodeSummaryDto[]
}

function buildPath(filters: EpisodeListFilters): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === '') continue
    params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `/api/v1/episodes?${qs}` : '/api/v1/episodes'
}

export function useEpisodeList(
  filters: EpisodeListFilters = {},
): UseQueryResult<EpisodeSummaryViewModel[], ApiErrorViewModel> {
  return useQuery<EpisodeSummaryViewModel[], ApiErrorViewModel>({
    queryKey: episodeKeys.list(filters as Record<string, unknown>),
    queryFn: async ({ signal }) => {
      const dto = await apiFetch<EpisodeListEnvelope>(buildPath(filters), { signal })
      return dto.items.map(toEpisodeSummary)
    },
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  })
}
