/**
 * App shell — TopBar (含 inline nav) + main content。
 *
 * 接受 locale / theme 狀態 + 變更 callback；持久化由 App.tsx 透過 UserPreferences 處理。
 */

import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet } from 'react-router-dom'

import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { KeyboardShortcutsHelp } from '@/components/common/KeyboardShortcutsHelp'
import type { SupportedLocale } from '@/i18n'
import type { ThemePreference } from '@/theme/applyTheme'

import { TopBar } from './TopBar'

export interface AppShellProps {
  locale: SupportedLocale
  onLocaleChange: (locale: SupportedLocale) => void
  themePreference: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
}

export function AppShell({
  locale,
  onLocaleChange,
  themePreference,
  onThemeChange,
}: AppShellProps) {
  const { i18n, t } = useTranslation()

  useEffect(() => {
    if (i18n.language !== locale) void i18n.changeLanguage(locale)
  }, [i18n, locale])

  return (
    <div className="flex h-screen flex-col bg-bg-base text-text-primary">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-tooltip focus:rounded-sm focus:bg-primary focus:px-md focus:py-sm focus:text-white"
      >
        {t('nav.skipToMain')}
      </a>

      <TopBar
        locale={locale}
        onLocaleChange={onLocaleChange}
        themePreference={themePreference}
        onThemeChange={onThemeChange}
      />

      <main
        id="main-content"
        className="flex-1 overflow-auto px-4 py-4 lg:px-5 lg:py-5"
        role="main"
      >
        <div className="mx-auto max-w-[1920px]">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>

      <KeyboardShortcutsHelp />
    </div>
  )
}
