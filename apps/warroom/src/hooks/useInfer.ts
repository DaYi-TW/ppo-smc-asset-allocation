/**
 * useInfer — POST /api/v1/infer mutation。
 *
 * 自動產生 Idempotency-Key（重試同一 observation 不會重複扣 quota）。
 */

import { useMutation, type UseMutationResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { inferKeys } from '@/api/queryKeys'
import type { InferActionDto, InferRequestDto } from '@/api/types.gen'
import type { ApiErrorViewModel } from '@/viewmodels/error'

function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `infer-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function useInfer(
  policyId: string,
): UseMutationResult<InferActionDto, ApiErrorViewModel, InferRequestDto> {
  return useMutation<InferActionDto, ApiErrorViewModel, InferRequestDto>({
    mutationKey: inferKeys.invoke(policyId),
    mutationFn: (req) =>
      apiFetch<InferActionDto>('/api/v1/infer', {
        method: 'POST',
        body: req,
        idempotencyKey: generateIdempotencyKey(),
      }),
  })
}
