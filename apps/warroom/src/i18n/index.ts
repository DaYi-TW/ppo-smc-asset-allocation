/**
 * i18next initialisation — namespace `translation`，預設語言 zh-TW。
 *
 * 對應 contracts/i18n-keys.md。
 * 語言偏好由 viewmodels/policy.ts 的 UserPreferences 持有，
 * Settings 頁變更時呼叫 i18n.changeLanguage()。
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enMessages from './locales/en.json'
import zhTwMessages from './locales/zh-TW.json'

export type SupportedLocale = 'zh-TW' | 'en'

export const SUPPORTED_LOCALES: readonly SupportedLocale[] = ['zh-TW', 'en'] as const

export const DEFAULT_LOCALE: SupportedLocale = 'zh-TW'

void i18n.use(initReactI18next).init({
  resources: {
    'zh-TW': { translation: zhTwMessages },
    en: { translation: enMessages },
  },
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: {
    escapeValue: false,
  },
  returnNull: false,
})

export default i18n
