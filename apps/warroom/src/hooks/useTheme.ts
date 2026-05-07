/**
 * useTheme — 整合 useUserPrefs + applyTheme + system 監聽。
 *
 * 副作用：
 *  - preferences.theme 變更時呼叫 applyTheme（toggle <html> .dark）
 *  - theme === 'system' 時訂閱 prefers-color-scheme 變化
 *
 * 回傳 resolvedMode（'light' | 'dark'）供 chart 即時讀取。
 */

import { useEffect, useState } from 'react'

import { applyTheme, watchSystemTheme } from '@/theme/applyTheme'
import type { ThemeMode } from '@/theme/tokens'
import type { ThemePreference } from '@/viewmodels/policy'

export interface UseThemeReturn {
  resolvedMode: ThemeMode
}

export function useTheme(preference: ThemePreference): UseThemeReturn {
  const [resolvedMode, setResolvedMode] = useState<ThemeMode>(() => applyTheme(preference))

  useEffect(() => {
    setResolvedMode(applyTheme(preference))
  }, [preference])

  useEffect(() => {
    if (preference !== 'system') return
    return watchSystemTheme((mode) => {
      setResolvedMode(applyTheme('system'))
      void mode
    })
  }, [preference])

  return { resolvedMode }
}
