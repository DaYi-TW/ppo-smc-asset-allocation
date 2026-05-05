/**
 * App root — hash router、UserPreferences 持久化、theme 套用。
 *
 * 路由配置：
 *  - / → /overview（redirect）
 *  - /overview     OverviewPage
 *  - /trajectory   TrajectoryPage
 *  - /decision     DecisionPage
 *  - /settings     SettingsPage
 */

import { useCallback, useEffect, useMemo } from 'react'
import { createHashRouter, Navigate, RouterProvider } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { useTheme } from '@/hooks/useTheme'
import { useUserPrefs } from '@/hooks/useUserPrefs'
import i18n, { type SupportedLocale } from '@/i18n'
import { DecisionPage } from '@/pages/DecisionPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TrajectoryPage } from '@/pages/TrajectoryPage'
import type { ThemePreference } from '@/theme/applyTheme'

export function App() {
  const { preferences, updatePreference } = useUserPrefs()

  useTheme(preferences.theme)

  useEffect(() => {
    if (i18n.language !== preferences.language) {
      void i18n.changeLanguage(preferences.language)
    }
  }, [preferences.language])

  const handleLocaleChange = useCallback(
    (locale: SupportedLocale) => {
      updatePreference('language', locale)
    },
    [updatePreference],
  )

  const handleThemeChange = useCallback(
    (theme: ThemePreference) => {
      updatePreference('theme', theme)
    },
    [updatePreference],
  )

  const router = useMemo(
    () =>
      createHashRouter([
        {
          path: '/',
          element: (
            <AppShell
              locale={preferences.language}
              onLocaleChange={handleLocaleChange}
              themePreference={preferences.theme}
              onThemeChange={handleThemeChange}
            />
          ),
          children: [
            { index: true, element: <Navigate to="/overview" replace /> },
            { path: 'overview', element: <OverviewPage /> },
            { path: 'trajectory', element: <TrajectoryPage /> },
            { path: 'decision', element: <DecisionPage /> },
            { path: 'settings', element: <SettingsPage /> },
            { path: '*', element: <Navigate to="/overview" replace /> },
          ],
        },
      ]),
    [preferences.language, preferences.theme, handleLocaleChange, handleThemeChange],
  )

  return <RouterProvider router={router} />
}
