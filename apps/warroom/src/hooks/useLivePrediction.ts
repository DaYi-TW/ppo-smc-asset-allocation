/**
 * useLivePrediction — 整合 006 Gateway 三條路徑：
 *   1. GET  /api/v1/inference/latest     初始 latest snapshot（mount 時）
 *   2. SSE  /api/v1/predictions/stream   訂閱即時更新（005 publish 到 Redis 後 fanout）
 *   3. POST /api/v1/inference/run        手動「立即重跑」按鈕
 *
 * 任一路徑成功即把最新 PredictionPayload 寫入 React Query cache，UI 對齊單一來源。
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useEffect } from 'react'

import { getLatestPrediction, runInference } from '@/api/inference'
import { openSse } from '@/api/sse'
import type { PredictionPayload, PredictionStreamEvent } from '@/viewmodels/prediction'
import type { ApiErrorViewModel } from '@/viewmodels/error'

export const livePredictionKey = ['inference', 'latest'] as const

function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `infer-run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export interface UseLivePredictionResult {
  latest: UseQueryResult<PredictionPayload, ApiErrorViewModel>
  run: UseMutationResult<PredictionPayload, ApiErrorViewModel, void>
}

export function useLivePrediction(): UseLivePredictionResult {
  const queryClient = useQueryClient()

  const latest = useQuery<PredictionPayload, ApiErrorViewModel>({
    queryKey: livePredictionKey,
    queryFn: getLatestPrediction,
    // 404 PredictionNotReady 是合法初始狀態，不要無限 retry
    retry: (failureCount, error) =>
      error.httpStatus !== 404 && error.retryable && failureCount < 2,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  })

  // SSE：把 server push 寫進同一個 cache key，UI 自動 re-render
  useEffect(() => {
    const handle = openSse<PredictionStreamEvent>({
      url: '/api/v1/predictions/stream',
      eventName: 'prediction',
      onEvent: (ev) => {
        if (ev.payload) {
          queryClient.setQueryData<PredictionPayload>(livePredictionKey, ev.payload)
        }
      },
    })
    return () => handle.close()
  }, [queryClient])

  const run = useMutation<PredictionPayload, ApiErrorViewModel, void>({
    mutationFn: () => runInference(generateIdempotencyKey()),
    onSuccess: (payload) => {
      queryClient.setQueryData<PredictionPayload>(livePredictionKey, payload)
    },
  })

  return { latest, run }
}
