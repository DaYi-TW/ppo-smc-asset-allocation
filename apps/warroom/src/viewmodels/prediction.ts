/**
 * LivePrediction view models — 對齊 006 Spring Gateway camelCase JSON
 * （`specs/006-spring-gateway/contracts/openapi.yaml` PredictionPayload schema）。
 *
 * 005 內部用 snake_case；006 Gateway 已轉成 camelCase 給前端，因此本檔不再做欄位
 * 對映，僅定義 view-friendly 型別。
 */

export type TriggeredBy = 'manual' | 'scheduled'

export interface PredictionContext {
  dataRoot: string
  includeSmc: boolean
  nWarmupSteps: number
  /** 推理當下（asOfDate）對應的 NAV，用於前端校驗、回溯 */
  currentNavAtAsOf: number
}

export interface PredictionPayload {
  asOfDate: string
  nextTradingDayTarget: string
  policyPath: string
  deterministic: boolean
  /** ticker → weight，七檔資產（NVDA / AMD / TSM / MU / GLD / TLT / CASH 等）總和趨近 1 */
  targetWeights: Record<string, number>
  weightsCapped: boolean
  renormalized: boolean
  context: PredictionContext
  triggeredBy: TriggeredBy
  inferenceId: string
  inferredAtUtc: string
}

/** SSE event payload — 對齊 PredictionEventDto */
export interface PredictionStreamEvent {
  eventType: string
  emittedAtUtc: string
  payload: PredictionPayload | null
}
