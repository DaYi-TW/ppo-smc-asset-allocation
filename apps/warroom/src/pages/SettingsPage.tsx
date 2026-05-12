/**
 * Settings page — 偏好設定（語言、主題、預設 policy、時區）。
 *
 * 透過 useUserPrefs 持久化於 localStorage；變更立即生效（無需 reload）。
 */

import { useTranslation } from 'react-i18next'

import { LivePredictionCard } from '@/components/panels/LivePredictionCard'
import { useTheme } from '@/hooks/useTheme'
import { useUserPrefs } from '@/hooks/useUserPrefs'
import { SUPPORTED_LOCALES, type SupportedLocale } from '@/i18n'
import type { ThemePreference, TimezonePreference } from '@/viewmodels/policy'

export function SettingsPage() {
  const { t } = useTranslation()
  const { preferences, updatePreference, reset } = useUserPrefs()
  useTheme(preferences.theme)

  return (
    <section aria-labelledby="settings-heading" className="flex flex-col gap-lg">
      <h2 id="settings-heading" className="text-2xl font-semibold text-text-primary">
        {t('settings.title')}
      </h2>

      <div className="flex flex-col gap-md max-w-xl">
        <label className="flex flex-col gap-xs">
          <span className="text-sm text-text-secondary">{t('settings.language.label')}</span>
          <select
            value={preferences.language}
            onChange={(e) => updatePreference('language', e.target.value as SupportedLocale)}
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

        <label className="flex flex-col gap-xs">
          <span className="text-sm text-text-secondary">{t('settings.theme.label')}</span>
          <select
            value={preferences.theme}
            onChange={(e) => updatePreference('theme', e.target.value as ThemePreference)}
            className="rounded-sm bg-bg-elevated text-text-primary border border-default px-sm py-1"
            aria-label={t('settings.theme.label')}
          >
            <option value="system">{t('settings.theme.system')}</option>
            <option value="light">{t('settings.theme.light')}</option>
            <option value="dark">{t('settings.theme.dark')}</option>
          </select>
        </label>

        <label className="flex flex-col gap-xs">
          <span className="text-sm text-text-secondary">{t('settings.timezone.label')}</span>
          <select
            value={preferences.timezone}
            onChange={(e) => updatePreference('timezone', e.target.value as TimezonePreference)}
            className="rounded-sm bg-bg-elevated text-text-primary border border-default px-sm py-1"
            aria-label={t('settings.timezone.label')}
          >
            <option value="UTC">{t('settings.timezone.utc')}</option>
            <option value="local">{t('settings.timezone.local')}</option>
          </select>
        </label>

        <button
          type="button"
          onClick={reset}
          className="self-start rounded-sm border border-default px-md py-xs text-sm text-text-secondary hover:bg-bg-elevated"
        >
          {t('app.cancel')}
        </button>
      </div>

      <LivePredictionCard />
    </section>
  )
}
