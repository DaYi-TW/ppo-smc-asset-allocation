/**
 * Policy 與使用者偏好 ViewModel — 對應 data-model.md §6 / §8。
 */

export interface PolicyMetrics {
  sharpeRatio: number
  maxDrawdown: number
  cumulativeReturn: number
}

export interface PolicyOption {
  policyId: string
  policyVersion: string
  displayName: string
  trainedAt: string
  trainingDataRange: { start: string; end: string }
  configSummary: string
  metrics: PolicyMetrics
  active: boolean
}

export type ThemePreference = 'light' | 'dark' | 'system'
export type LanguagePreference = 'zh-TW' | 'en'
export type NumberLocale = 'en-US' | 'zh-TW'
export type TimezonePreference = 'UTC' | 'local'

export interface UserPreferences {
  language: LanguagePreference
  theme: ThemePreference
  defaultPolicyId?: string
  chartGridlines: boolean
  numberLocale: NumberLocale
  timezone: TimezonePreference
}

export const DEFAULT_PREFERENCES: UserPreferences = {
  language: 'zh-TW',
  theme: 'system',
  chartGridlines: true,
  numberLocale: 'en-US',
  timezone: 'UTC',
}

export const PREFERENCES_STORAGE_KEY = 'warroom.preferences.v1'
