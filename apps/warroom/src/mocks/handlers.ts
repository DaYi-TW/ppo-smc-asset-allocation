/**
 * MSW request handlers — 對應 contracts/api-mapping.md 的端點清單。
 *
 * 檔次 2-local 預設啟用（VITE_USE_MOCK=true），不接 006 真實 Gateway。
 * 待 005/006 ready 後改 VITE_USE_MOCK=false 即可走真實 API。
 *
 * Episodes endpoints 已對齊 005/006 真實 wire format（feature 009）：
 *   - GET /api/v1/episodes 回 EpisodeListEnvelopeDto（{items, meta}）
 *   - GET /api/v1/episodes/{id} 回 EpisodeDetailEnvelopeDto（{data, meta}）
 * Fixture 仍是 legacy schema，handler 在 response 階段做包裝 + 欄位翻譯。
 */

import { http, HttpResponse, delay } from 'msw'

import type {
  EpisodeDetailEnvelopeDto,
  EpisodeListEnvelopeDto,
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

interface LegacyEpisodeSummary {
  episodeId: string
  policyId: string
  startDate: string
  endDate: string
  totalReturn: number
  maxDrawdown: number
  sharpeRatio: number
  totalSteps: number
}

interface LegacyEpisodeList {
  items: LegacyEpisodeSummary[]
}

interface LegacyEpisodeDetail extends LegacyEpisodeSummary {
  trajectoryInline?: unknown[]
  rewardBreakdown?: { byStep?: unknown[]; cumulative?: unknown[] }
  smcOverlayByAsset?: Record<string, unknown>
}

const policiesData = policies as PolicyMetadataDto[]
const episodeListData = episodeList as unknown as LegacyEpisodeList
const episodeDetailData = episodeDetail as unknown as LegacyEpisodeDetail
const predictionLatestData = predictionLatest as PredictionPayload

function legacyToWireSummary(s: LegacyEpisodeSummary): EpisodeSummaryDto {
  // legacy totalReturn 為 cumulative log-return（非 %）；wire format 是百分比.
  const cumulativeReturnPct = s.totalReturn * 100
  const maxDrawdownPct = Math.abs(s.maxDrawdown) * 100
  return {
    id: s.episodeId,
    policyId: s.policyId,
    startDate: s.startDate,
    endDate: s.endDate,
    nSteps: s.totalSteps,
    initialNav: 1.0,
    finalNav: 1 + s.totalReturn,
    cumulativeReturnPct,
    annualizedReturnPct: cumulativeReturnPct,
    maxDrawdownPct,
    sharpeRatio: s.sharpeRatio,
    sortinoRatio: s.sharpeRatio,
    includeSmc: true,
  }
}

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
    const env: EpisodeListEnvelopeDto = {
      items: episodeListData.items.map(legacyToWireSummary),
      meta: { count: episodeListData.items.length, generatedAt: new Date().toISOString() },
    }
    return HttpResponse.json(env)
  }),

  http.get(`${API_BASE}/api/v1/episodes/:id`, async ({ params }) => {
    await delay(120)
    if (params.id !== episodeDetailData.episodeId) {
      return notFound('EPISODE_NOT_FOUND', `Episode ${String(params.id)} not found`)
    }
    const env: EpisodeDetailEnvelopeDto = {
      data: {
        summary: legacyToWireSummary(episodeDetailData),
        // legacy fixture's nested DTOs already align field names; cast to bypass strict
        // typing — production wire validation happens at 005 boundary, not in mock.
        trajectoryInline: (episodeDetailData.trajectoryInline ?? []) as never,
        rewardBreakdown: {
          byStep: (episodeDetailData.rewardBreakdown?.byStep ?? []) as never,
          cumulative: (episodeDetailData.rewardBreakdown?.cumulative ?? []) as never,
        },
        smcOverlayByAsset: (episodeDetailData.smcOverlayByAsset ?? {}) as never,
      },
      meta: { generatedAt: new Date().toISOString() },
    }
    return HttpResponse.json(env)
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
