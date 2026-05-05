/**
 * TopBar — 對應 mockup `.topbar`：
 *   [● PPO-SMC War Room v0.x.x · 2026-XX-XX]   [總覽 回測 SMC ...]   [pill] [Kafka] [symbols]
 *
 * 三段：
 *  - 左：brand dot + title + sub
 *  - 中：inline nav（NavLink active = bg-bg-elevated）
 *  - 右：連線 pill（pulse led）+ Kafka rate + 標的清單 + locale/theme select
 */

import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'

import { SUPPORTED_LOCALES, type SupportedLocale } from '@/i18n'
import type { ThemePreference } from '@/theme/applyTheme'

export interface TopBarProps {
  locale: SupportedLocale
  onLocaleChange: (locale: SupportedLocale) => void
  themePreference: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
}

interface NavItem {
  to: string
  i18nKey: string
}

const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { to: '/overview', i18nKey: 'nav.overview' },
  { to: '/trajectory', i18nKey: 'nav.trajectory' },
  { to: '/decision', i18nKey: 'nav.decision' },
  { to: '/settings', i18nKey: 'nav.settings' },
]

const SYMBOLS = 'NVDA · AMD · TSM · MU · GLD · TLT'

export function TopBar({
  locale,
  onLocaleChange,
  themePreference,
  onThemeChange,
}: TopBarProps) {
  const { t } = useTranslation()

  return (
    <header
      className="sticky top-0 z-40 flex min-h-[56px] flex-wrap items-center gap-3 border-b border-border bg-bg-surface px-4"
      role="banner"
    >
      <div className="flex flex-shrink-0 items-center gap-2.5">
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 rounded-full bg-info"
          style={{ boxShadow: '0 0 12px var(--color-info)' }}
        />
        <span className="text-[15px] font-bold tracking-wide text-text-primary">
          {t('app.title')}
        </span>
        <span className="hidden text-xs text-text-secondary sm:inline">
          {t('app.subtitle')}
        </span>
      </div>

      <nav className="flex flex-wrap gap-1" aria-label={t('nav.overview')}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'inline-flex min-h-[36px] items-center whitespace-nowrap rounded px-3 py-1.5 text-sm transition-colors',
                isActive
                  ? 'bg-bg-elevated text-text-primary'
                  : 'text-text-secondary hover:bg-bg-elevated/50 hover:text-text-primary',
              ].join(' ')
            }
          >
            {t(item.i18nKey)}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex flex-wrap items-center justify-end gap-3 text-xs text-text-secondary">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg-elevated px-2.5 py-1">
          <span
            aria-hidden="true"
            className="h-2 w-2 animate-pulse rounded-full bg-success"
            style={{ boxShadow: '0 0 8px var(--color-success)' }}
          />
          {t('topbar.aiEngine')}
        </span>
        <span className="hidden md:inline">{t('topbar.kafkaRate', { rate: '12.4' })}</span>
        <span className="hidden lg:inline">{SYMBOLS}</span>

        <select
          value={locale}
          onChange={(e) => onLocaleChange(e.target.value as SupportedLocale)}
          className="rounded border border-border bg-bg-elevated px-2 py-1 text-xs text-text-primary"
          aria-label={t('settings.language.label')}
        >
          {SUPPORTED_LOCALES.map((loc) => (
            <option key={loc} value={loc}>
              {loc === 'zh-TW' ? t('settings.language.zhTW') : t('settings.language.en')}
            </option>
          ))}
        </select>
        <select
          value={themePreference}
          onChange={(e) => onThemeChange(e.target.value as ThemePreference)}
          className="rounded border border-border bg-bg-elevated px-2 py-1 text-xs text-text-primary"
          aria-label={t('settings.theme.label')}
        >
          <option value="system">{t('settings.theme.system')}</option>
          <option value="light">{t('settings.theme.light')}</option>
          <option value="dark">{t('settings.theme.dark')}</option>
        </select>
      </div>
    </header>
  )
}
