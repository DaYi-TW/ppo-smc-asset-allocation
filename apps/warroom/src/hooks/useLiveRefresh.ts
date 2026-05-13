/**
 * Feature 010 — useLiveRefresh hook：
 *   - useQuery 抓 GET /live/status，閒置時 60s polling、pipeline 在跑時切 3s（R11）
 *   - useMutation 觸發 POST /live/refresh
 *   - 結算後 invalidate status 拉一次（讓 isRunning=true 馬上反映）
 *   - 偵測到 isRunning 從 true → false 的 falling edge 時，invalidate detail 讓 OverviewPage 重抓
 *
 * 設計要點：
 *   1. mutation 結果是 RefreshResult discriminated union，不把 conflict 當失敗 — UI 會根據
 *      result.status 切 toast 文案（FR-024 / FR-025）
 *   2. POST /refresh 回 202 時 pipeline 還在 background 跑 → 不能在 onSettled 立刻 invalidate detail，
 *      會搶在 artefact 寫完前抓到舊資料。改成 watch status.isRunning falling edge
 *   3. 全程 React Query cache 一致：status query 變動 → DataLagBadge / LiveRefreshButton 自動 re-render
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

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
      // 立刻拉一次 status 反映 isRunning=true。detail invalidate 留給 falling edge effect
      queryClient.invalidateQueries({ queryKey: liveStatusKey })
    },
  })

  // 監聽 isRunning true → false 的 falling edge：pipeline 真的跑完，才 invalidate detail 重抓
  const prevRunningRef = useRef<boolean>(false)
  const isRunning = status.data?.isRunning ?? false
  useEffect(() => {
    if (prevRunningRef.current && !isRunning && liveEpisodeId) {
      queryClient.invalidateQueries({ queryKey: liveDetailKey(liveEpisodeId) })
    }
    prevRunningRef.current = isRunning
  }, [isRunning, liveEpisodeId, queryClient])

  return { status, refresh }
}
