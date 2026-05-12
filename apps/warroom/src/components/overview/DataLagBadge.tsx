/**
 * Feature 010 FR-022 / SC-003 — 「資料截至 N 天前」badge.
 *
 * 三種狀態：
 *   - dataLagDays === null → 「Live tracking 尚未啟動」（從未跑過）
 *   - dataLagDays === 0    → 「最新」（綠）
 *   - dataLagDays >  0     → 「N 天前」（黃 / 紅 取決於 N）
 *
 * 純 presentational — 資料來自 useLiveRefresh().status。i18n key 對齊
 * apps/warroom/src/i18n/translations/*.json（fallback 中文）。
 */

import { useTranslation } from 'react-i18next'

export interface DataLagBadgeProps {
  dataLagDays: number | null
}

export function DataLagBadge({ dataLagDays }: DataLagBadgeProps) {
  const { t } = useTranslation()

  if (dataLagDays === null) {
    return (
      <span
        data-testid="data-lag-badge"
        className="inline-flex items-center rounded-full border border-border bg-surface px-sm py-xs text-xs text-text-secondary"
      >
        {t('liveTracking.lag.notStarted', 'Live tracking 尚未啟動')}
      </span>
    )
  }

  if (dataLagDays === 0) {
    return (
      <span
        data-testid="data-lag-badge"
        className="inline-flex items-center rounded-full border border-success/40 bg-success/10 px-sm py-xs text-xs text-success"
      >
        {t('liveTracking.lag.fresh', '最新')}
      </span>
    )
  }

  const tone =
    dataLagDays <= 2
      ? 'border-warning/40 bg-warning/10 text-warning'
      : 'border-danger/40 bg-danger/10 text-danger'

  return (
    <span
      data-testid="data-lag-badge"
      className={`inline-flex items-center rounded-full border px-sm py-xs text-xs ${tone}`}
    >
      {t('liveTracking.lag.daysAgo', '{{n}} 天前', { n: dataLagDays })}
    </span>
  )
}
