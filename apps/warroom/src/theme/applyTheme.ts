/**
 * Theme application — 切 <html> class，並可選監聽系統 prefers-color-scheme。
 *
 * 對應 contracts/theme-tokens.md「主題切換邏輯」章節。
 */

import type { ThemePreference } from '@/viewmodels/policy'

import type { ThemeMode } from './tokens'

export type { ThemePreference } from '@/viewmodels/policy'

const DARK_QUERY = '(prefers-color-scheme: dark)'

export function resolveTheme(pref: ThemePreference): ThemeMode {
  if (pref === 'system') {
    return typeof window !== 'undefined' && window.matchMedia(DARK_QUERY).matches
      ? 'dark'
      : 'light'
  }
  return pref
}

export function applyTheme(pref: ThemePreference): ThemeMode {
  const resolved = resolveTheme(pref)
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
  }
  return resolved
}

/**
 * 監聽系統色彩模式變化（僅 pref==='system' 時意義最大）。
 * 回傳 unsubscribe；於 React effect cleanup 呼叫。
 */
export function watchSystemTheme(onChange: (mode: ThemeMode) => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const mq = window.matchMedia(DARK_QUERY)
  const handler = (ev: MediaQueryListEvent) => onChange(ev.matches ? 'dark' : 'light')
  mq.addEventListener('change', handler)
  return () => mq.removeEventListener('change', handler)
}
