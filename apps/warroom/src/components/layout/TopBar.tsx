/**
 * 頂部 bar — app title、語言切換、主題切換、目前 episode 顯示位（將於 US1 接入）。
 */

import { useTranslation } from 'react-i18next'

import { SUPPORTED_LOCALES, type SupportedLocale } from '@/i18n'
import type { ThemePreference } from '@/theme/applyTheme'

export interface TopBarProps {
  locale: SupportedLocale
  onLocaleChange: (locale: SupportedLocale) => void
  themePreference: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
}

export function TopBar({
  locale,
  onLocaleChange,
  themePreference,
  onThemeChange,
}: TopBarProps) {
  const { t } = useTranslation()

  return (
    <header
      className="flex items-center justify-between gap-md px-lg py-md border-b border-default bg-bg-surface"
      role="banner"
    >
      <div>
        <h1 className="text-xl font-semibold text-text-primary">{t('app.title')}</h1>
        <p className="text-xs text-text-muted">{t('app.subtitle')}</p>
      </div>

      <div className="flex items-center gap-md">
        <label className="flex items-center gap-sm text-sm text-text-secondary">
          <span className="sr-only">{t('settings.language.label')}</span>
          <select
            value={locale}
            onChange={(e) => onLocaleChange(e.target.value as SupportedLocale)}
            className="rounded-sm bg-bg-elevated text-text-primary border border-default px-sm py-1"
            aria-label={t('settings.language.label')}
          >
            {SUPPORTED_LOCALES.map((loc) => (
              <option key={loc} value={loc}>
                {loc === 'zh-TW' ? t('settings.language.zhTW') : t('settings.language.en')}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-sm text-sm text-text-secondary">
          <span className="sr-only">{t('settings.theme.label')}</span>
          <select
            value={themePreference}
            onChange={(e) => onThemeChange(e.target.value as ThemePreference)}
            className="rounded-sm bg-bg-elevated text-text-primary border border-default px-sm py-1"
            aria-label={t('settings.theme.label')}
          >
            <option value="system">{t('settings.theme.system')}</option>
            <option value="light">{t('settings.theme.light')}</option>
            <option value="dark">{t('settings.theme.dark')}</option>
          </select>
        </label>
      </div>
    </header>
  )
}
