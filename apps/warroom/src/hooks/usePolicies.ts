/**
 * usePolicies — GET /api/v1/policies
 *
 * 對應 contracts/api-mapping.md。回傳 PolicyOption[]，錯誤統一為 ApiErrorViewModel
 * （由 client.ts 拋出 ApiError 物件，React Query 會 unwrap viewModel）。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { apiFetch } from '@/api/client'
import { toPolicyOption } from '@/api/envelopes'
import { policyKeys } from '@/api/queryKeys'
import type { PolicyMetadataDto } from '@/api/types.gen'
import { ApiError, type ApiErrorViewModel } from '@/viewmodels/error'
import type { PolicyOption } from '@/viewmodels/policy'

interface PolicyListEnvelope {
  items: PolicyMetadataDto[]
}

export function usePolicies(): UseQueryResult<PolicyOption[], ApiErrorViewModel> {
  return useQuery<PolicyOption[], ApiErrorViewModel>({
    queryKey: policyKeys.list(),
    queryFn: async ({ signal }) => {
      try {
        const dto = await apiFetch<PolicyListEnvelope>('/api/v1/policies', { signal })
        return dto.items.map(toPolicyOption)
      } catch (err) {
        if (err instanceof ApiError && (err.viewModel.httpStatus === 404 || err.viewModel.httpStatus === 500)) {
          return []
        }
        throw err
      }
    },
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
  })
}
