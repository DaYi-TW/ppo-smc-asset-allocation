/**
 * 推論請求／回應 ViewModel — 對應 data-model.md §7。
 * 對應後端 005 inference-service 透過 006 gateway 暴露之 POST /api/v1/infer。
 */

import type { ActionVector } from './trajectory'

export interface InferRequestViewModel {
  policyId: string
  policyVersion?: string
  observation: number[]
  idempotencyKey?: string
}

export interface InferResponseViewModel {
  action: ActionVector
  policyId: string
  policyVersion: string
  inferredAt: string
  latencyMs: number
}
