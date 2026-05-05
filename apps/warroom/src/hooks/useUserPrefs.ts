/**
 * useUserPrefs — localStorage-backed user preferences hook（對應 data-model §8）。
 *
 * 跨頁同步：透過 storage event 監聽其他分頁的修改。
 */

import { useCallback, useEffect, useState } from 'react'

import {
  DEFAULT_PREFERENCES,
  PREFERENCES_STORAGE_KEY,
  type UserPreferences,
} from '@/viewmodels/policy'

function loadPreferences(): UserPreferences {
  if (typeof window === 'undefined') return DEFAULT_PREFERENCES
  try {
    const raw = window.localStorage.getItem(PREFERENCES_STORAGE_KEY)
    if (!raw) return DEFAULT_PREFERENCES
    const parsed = JSON.parse(raw) as Partial<UserPreferences>
    return { ...DEFAULT_PREFERENCES, ...parsed }
  } catch {
    return DEFAULT_PREFERENCES
  }
}

function savePreferences(prefs: UserPreferences): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(prefs))
}

export interface UseUserPrefsReturn {
  preferences: UserPreferences
  setPreferences: (next: UserPreferences) => void
  updatePreference: <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => void
  reset: () => void
}

export function useUserPrefs(): UseUserPrefsReturn {
  const [preferences, setPreferencesState] = useState<UserPreferences>(() => loadPreferences())

  useEffect(() => {
    savePreferences(preferences)
  }, [preferences])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (ev: StorageEvent) => {
      if (ev.key !== PREFERENCES_STORAGE_KEY) return
      setPreferencesState(loadPreferences())
    }
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])

  const setPreferences = useCallback((next: UserPreferences) => {
    setPreferencesState(next)
  }, [])

  const updatePreference = useCallback(
    <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
      setPreferencesState((prev) => ({ ...prev, [key]: value }))
    },
    [],
  )

  const reset = useCallback(() => {
    setPreferencesState(DEFAULT_PREFERENCES)
  }, [])

  return { preferences, setPreferences, updatePreference, reset }
}
