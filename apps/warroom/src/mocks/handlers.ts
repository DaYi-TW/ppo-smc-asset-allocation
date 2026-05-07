/**
 * MSW request handlers — 對應 contracts/api-mapping.md 的端點清單。
 *
 * 檔次 2-local 預設啟用（VITE_USE_MOCK=true），不接 006 真實 Gateway。
 * 待 005/006 ready 後改 VITE_USE_MOCK=false 即可走真實 API。
 */

import { http, HttpResponse, delay } from 'msw'

import type {
  EpisodeDetailDto,
  EpisodeSummaryDto,
  ErrorEnvelopeDto,
  InferActionDto,
  InferRequestDto,
  PolicyMetadataDto,
} from '@/api/types.gen'
import type { PredictionPayload } from '@/viewmodels/prediction'

import episodeDetail from './fixtures/episode-detail.json'
import episodeList from './fixtures/episode-list.json'
import policies from './fixtures/policies.json'
import predictionLatest from './fixtures/prediction-latest.json'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'

const policiesData = policies as PolicyMetadataDto[]
const episodeListData = episodeList as { items: EpisodeSummaryDto[] }
const episodeDetailData = episodeDetail as EpisodeDetailDto
const predictionLatestData = predictionLatest as PredictionPayload

function notFound(code: string, message: string) {
  const body: ErrorEnvelopeDto = {
    code,
    message,
    httpStatus: 404,
    traceId: 'mock-trace',
  }
  return HttpResponse.json(body, { status: 404 })
}

export const handlers = [
  http.get(`${API_BASE}/api/v1/health`, () => HttpResponse.json({ status: 'UP' })),

  http.get(`${API_BASE}/api/v1/policies`, async () => {
    await delay(50)
    return HttpResponse.json({ items: policiesData })
  }),

  http.get(`${API_BASE}/api/v1/policies/:id`, ({ params }) => {
    const policy = policiesData.find((p) => p.policyId === params.id)
    if (!policy) return notFound('POLICY_NOT_FOUND', `Policy ${String(params.id)} not found`)
    return HttpResponse.json(policy)
  }),

  http.get(`${API_BASE}/api/v1/episodes`, async () => {
    await delay(80)
    return HttpResponse.json(episodeListData)
  }),

  http.get(`${API_BASE}/api/v1/episodes/:id`, async ({ params }) => {
    await delay(120)
    if (params.id !== episodeDetailData.episodeId) {
      return notFound('EPISODE_NOT_FOUND', `Episode ${String(params.id)} not found`)
    }
    return HttpResponse.json(episodeDetailData)
  }),

  http.get(`${API_BASE}/api/v1/episodes/:id/trajectory`, async ({ params }) => {
    if (params.id !== episodeDetailData.episodeId) {
      return notFound('EPISODE_NOT_FOUND', `Episode ${String(params.id)} not found`)
    }
    return HttpResponse.json({
      episodeId: episodeDetailData.episodeId,
      frames: episodeDetailData.trajectoryInline ?? [],
    })
  }),

  http.post(`${API_BASE}/api/v1/infer`, async ({ request }) => {
    const body = (await request.json()) as InferRequestDto
    const policy = policiesData.find((p) => p.policyId === body.policyId)
    if (!policy) return notFound('POLICY_NOT_FOUND', `Policy ${body.policyId} not found`)
    // 假回應：把 observation 重新 normalised 為等分權重
    const dim = body.observation?.length ?? 7
    const equal = 1 / dim
    const action = Array.from({ length: dim }, () => equal)
    const resp: InferActionDto = {
      action: { raw: action, normalized: action, logProb: -1.78, entropy: 1.4 },
      policyId: policy.policyId,
      policyVersion: policy.policyVersion,
      inferredAt: new Date().toISOString(),
      latencyMs: 23,
    }
    await delay(120)
    return HttpResponse.json(resp)
  }),

  // 006 Gateway — Live Prediction endpoints
  http.get(`${API_BASE}/api/v1/inference/latest`, async () => {
    await delay(60)
    return HttpResponse.json(predictionLatestData)
  }),

  http.post(`${API_BASE}/api/v1/inference/run`, async () => {
    await delay(200)
    const payload: PredictionPayload = {
      ...predictionLatestData,
      triggeredBy: 'manual',
      inferenceId: `infer-mock-${Date.now()}`,
      inferredAtUtc: new Date().toISOString(),
    }
    return HttpResponse.json(payload)
  }),

  http.get(`${API_BASE}/api/v1/predictions/stream`, () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(': stream open\n\n'))
        // Mock 環境不主動 push event；保持連線開著即可。
        // 真實環境由 005 publish → Gateway fanout。
      },
    })
    return new HttpResponse(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    })
  }),
]
