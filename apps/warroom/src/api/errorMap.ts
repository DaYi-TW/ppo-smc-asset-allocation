/**
 * 錯誤 code → i18n key 對應 — 對應 contracts/i18n-keys.md。
 *
 * 找不到時 fallback 到 errors.unknown，不丟例外。
 */

import type { ApiErrorViewModel } from '@/viewmodels/error'

const ERROR_CODE_TO_I18N: Record<string, string> = {
  POLICY_NOT_FOUND: 'errors.policyNotFound',
  EPISODE_NOT_FOUND: 'errors.episodeNotFound',
  INVALID_OBSERVATION: 'errors.invalidObservation',
  INFER_TIMEOUT: 'errors.inferTimeout',
  RATE_LIMITED: 'errors.rateLimited',
  GATEWAY_UNAVAILABLE: 'errors.gatewayUnavailable',
  INFERENCE_SERVICE_DOWN: 'errors.inferenceServiceDown',
  VALIDATION_ERROR: 'errors.validationError',
  INTERNAL_ERROR: 'errors.internalError',
}

const RETRYABLE_CODES = new Set([
  'INFER_TIMEOUT',
  'RATE_LIMITED',
  'GATEWAY_UNAVAILABLE',
  'INFERENCE_SERVICE_DOWN',
  'INTERNAL_ERROR',
])

export function errorCodeToI18nKey(code: string): string {
  return ERROR_CODE_TO_I18N[code] ?? 'errors.unknown'
}

export function isRetryable(code: string, httpStatus: number): boolean {
  if (RETRYABLE_CODES.has(code)) return true
  return httpStatus >= 500 && httpStatus < 600
}

export function resolveErrorMessage(
  error: ApiErrorViewModel,
  t: (key: string, fallback?: string) => string,
): string {
  const i18nKey = error.i18nKey ?? errorCodeToI18nKey(error.code)
  const localized = t(i18nKey, error.message)
  return localized || error.message
}
