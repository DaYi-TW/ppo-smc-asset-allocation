/**
 * Feature 010 — useLiveRefresh hook：
 *   - useQuery 抓 GET /live/status，閒置時 60s polling、有 mutation 在跑時切 3s（R11）
 *   - useMutation 觸發 POST /live/refresh
 *   - 結算（success | conflict | error）後 invalidate live episode detail，讓 OverviewPage 重抓
 *
 * 設計要點：
 *   1. mutation 結果是 RefreshResult discriminated union，不把 conflict 當失敗 — UI 會根據
 *      result.status 切 toast 文案（FR-024 / FR-025）
 *   2. status.is_running=true 也代表 pipeline 在跑 → polling 加快（不只看 mutation isPending）
 *   3. 全程 React Query cache 一致：status query 變動 → DataLagBadge / LiveRefreshButton 自動 re-render
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'

import {
  fetchLiveStatus,
  triggerRefresh,
  type LiveTrackingStatus,
  type RefreshResult,
} from '@/api/episodes'

export const liveStatusKey = ['live', 'status'] as const
export const liveDetailKey = (episodeId: string) =>
  ['episode', 'detail', episodeId] as const

const POLL_IDLE_MS = 60_000
const POLL_INFLIGHT_MS = 3_000

export interface UseLiveRefreshResult {
  status: UseQueryResult<LiveTrackingStatus, Error>
  refresh: UseMutationResult<RefreshResult, Error, void>
}

export interface UseLiveRefreshOptions {
  /** 用於 refresh 完成後 invalidate live episode detail；若為 null 不 invalidate */
  liveEpisodeId?: string | null
}

export function useLiveRefresh(
  options: UseLiveRefreshOptions = {},
): UseLiveRefreshResult {
  const queryClient = useQueryClient()
  const { liveEpisodeId } = options

  const status = useQuery<LiveTrackingStatus, Error>({
    queryKey: liveStatusKey,
    queryFn: fetchLiveStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.isRunning ? POLL_INFLIGHT_MS : POLL_IDLE_MS
    },
    refetchOnWindowFocus: false,
    staleTime: 0,
  })

  const refresh = useMutation<RefreshResult, Error, void>({
    mutationFn: triggerRefresh,
    onSettled: () => {
      // 不論 accepted / conflict / error 都 invalidate — pipeline 可能已在跑，要重新對齊狀態
      queryClient.invalidateQueries({ queryKey: liveStatusKey })
      if (liveEpisodeId) {
        queryClient.invalidateQueries({ queryKey: liveDetailKey(liveEpisodeId) })
      }
    },
  })

  return { status, refresh }
}
