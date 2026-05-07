/**
 * useTrajectory — GET /api/v1/episodes/{id}/trajectory
 *
 * 與 useEpisodeDetail 不同：只取 frames，TTL 較長，便於 K 線/重播大量 hover。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { toTrajectoryFrame } from '@/api/envelopes'
import { episodeKeys } from '@/api/queryKeys'
import type { TrajectoryFrameDto } from '@/api/types.gen'
import type { ApiErrorViewModel } from '@/viewmodels/error'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

interface TrajectoryEnvelope {
  episodeId: string
  frames: TrajectoryFrameDto[]
}

export function useTrajectory(
  episodeId: string | undefined,
): UseQueryResult<TrajectoryFrame[], ApiErrorViewModel> {
  return useQuery<TrajectoryFrame[], ApiErrorViewModel>({
    queryKey: episodeKeys.trajectory(episodeId ?? '__none__'),
    queryFn: async ({ signal }) => {
      const dto = await apiFetch<TrajectoryEnvelope>(
        `/api/v1/episodes/${encodeURIComponent(episodeId as string)}/trajectory`,
        { signal },
      )
      return dto.frames.map(toTrajectoryFrame)
    },
    enabled: Boolean(episodeId),
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
  })
}
