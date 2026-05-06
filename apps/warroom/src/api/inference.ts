/**
 * 006 Spring Gateway inference REST endpoints。
 *
 * - POST /api/v1/inference/run     手動觸發一次推理（timeout 90s）
 * - GET  /api/v1/inference/latest  取最新一筆 cached prediction（5s）
 *
 * 兩者皆回 PredictionPayload（camelCase；對齊 contracts/openapi.yaml）。
 */

import { apiFetch } from './client'
import type { PredictionPayload } from '@/viewmodels/prediction'

/** 對應 Gateway 6 layer 全鏈：Gateway → 005 inference → predict.py → 005 cache write
 *  90 秒上限對齊 spec 005 SC-001（含 env warmup ~30s） */
const RUN_TIMEOUT_MS = 90_000
const LATEST_TIMEOUT_MS = 5_000

export async function runInference(idempotencyKey?: string): Promise<PredictionPayload> {
  const init: Parameters<typeof apiFetch>[1] = {
    method: 'POST',
    timeoutMs: RUN_TIMEOUT_MS,
  }
  if (idempotencyKey) init.idempotencyKey = idempotencyKey
  return apiFetch<PredictionPayload>('/api/v1/inference/run', init)
}

export async function getLatestPrediction(): Promise<PredictionPayload> {
  return apiFetch<PredictionPayload>('/api/v1/inference/latest', {
    method: 'GET',
    timeoutMs: LATEST_TIMEOUT_MS,
  })
}
