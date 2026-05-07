/**
 * 側邊導覽 — 4 個路由，hash routing。
 */

import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'

interface NavItem {
  to: string
  i18nKey: string
}

const ITEMS: ReadonlyArray<NavItem> = [
  { to: '/overview', i18nKey: 'nav.overview' },
  { to: '/trajectory', i18nKey: 'nav.trajectory' },
  { to: '/decision', i18nKey: 'nav.decision' },
  { to: '/settings', i18nKey: 'nav.settings' },
] as const

export function SideNav() {
  const { t } = useTranslation()
  return (
    <nav
      aria-label={t('nav.overview')}
      className="flex flex-col gap-xs p-md border-r border-default bg-bg-surface w-48"
    >
      {ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            [
              'rounded-sm px-md py-sm text-sm transition-colors',
              isActive
                ? 'bg-primary text-white'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary',
            ].join(' ')
          }
        >
          {t(item.i18nKey)}
        </NavLink>
      ))}
    </nav>
  )
}
