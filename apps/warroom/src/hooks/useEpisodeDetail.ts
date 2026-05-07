/**
 * useEpisodeDetail — GET /api/v1/episodes/{id}
 *
 * episodeId 為 falsy 時 query 不會 fire（避免 undefined→404）。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { toEpisodeDetail } from '@/api/envelopes'
import { episodeKeys } from '@/api/queryKeys'
import type { EpisodeDetailEnvelopeDto } from '@/api/types.gen'
import type { EpisodeDetailViewModel } from '@/viewmodels/episode'
import type { ApiErrorViewModel } from '@/viewmodels/error'

export function useEpisodeDetail(
  episodeId: string | undefined,
): UseQueryResult<EpisodeDetailViewModel, ApiErrorViewModel> {
  return useQuery<EpisodeDetailViewModel, ApiErrorViewModel>({
    queryKey: episodeKeys.detail(episodeId ?? '__none__'),
    queryFn: async ({ signal }) => {
      const envelope = await apiFetch<EpisodeDetailEnvelopeDto>(
        `/api/v1/episodes/${encodeURIComponent(episodeId as string)}`,
        { signal },
      )
      return toEpisodeDetail(envelope)
    },
    enabled: Boolean(episodeId),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  })
}
