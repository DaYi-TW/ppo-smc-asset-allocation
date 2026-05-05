/**
 * API 錯誤 ViewModel — 對應 data-model.md §9。
 * 由 src/api/envelopes.ts 之 toApiError() 從 006 Gateway 統一錯誤 envelope 轉換。
 */

export interface ApiErrorViewModel {
  code: string
  message: string
  i18nKey?: string
  httpStatus: number
  traceId: string
  details?: Record<string, unknown>
  retryable: boolean
}

/** 自製 Error 類別 — fetch wrapper 拋出時帶完整 ViewModel。 */
export class ApiError extends Error {
  readonly viewModel: ApiErrorViewModel

  constructor(viewModel: ApiErrorViewModel) {
    super(viewModel.message)
    this.name = 'ApiError'
    this.viewModel = viewModel
  }
}
