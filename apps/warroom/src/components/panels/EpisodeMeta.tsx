/**
 * EpisodeMeta — 顯示單一 episode 的關鍵績效摘要卡片。
 *
 * 對應 spec FR-008、FR-013：總報酬、Sharpe、最大回撤、總交易日。
 */

import { useTranslation } from 'react-i18next'

import { formatNumber, formatPercent } from '@/utils/format'
import type { EpisodeSummaryViewModel } from '@/viewmodels/episode'

export interface EpisodeMetaProps {
  episode: EpisodeSummaryViewModel
}

interface Card {
  label: string
  value: string
  tone?: 'default' | 'positive' | 'negative'
}

export function EpisodeMeta({ episode }: EpisodeMetaProps) {
  const { t } = useTranslation()

  const cards: Card[] = [
    {
      label: t('overview.summary.totalReturn'),
      value: formatPercent(episode.totalReturn, { fractionDigits: 2 }),
      tone: episode.totalReturn >= 0 ? 'positive' : 'negative',
    },
    {
      label: t('overview.summary.sharpeRatio'),
      value: formatNumber(episode.sharpeRatio, { fractionDigits: 2 }),
    },
    {
      label: t('overview.summary.maxDrawdown'),
      value: formatPercent(episode.maxDrawdown, { fractionDigits: 2 }),
      tone: 'negative',
    },
    {
      label: t('overview.summary.totalSteps'),
      value: formatNumber(episode.totalSteps, { fractionDigits: 0 }),
    },
  ]

  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label={t('overview.title')}>
      {cards.map((c) => (
        <div
          key={c.label}
          className="rounded-md border border-border bg-bg-surface p-3 shadow-sm"
        >
          <dt className="text-xs uppercase tracking-wide text-text-secondary">{c.label}</dt>
          <dd
            className={
              c.tone === 'positive'
                ? 'mt-1 text-lg font-semibold text-success'
                : c.tone === 'negative'
                  ? 'mt-1 text-lg font-semibold text-danger'
                  : 'mt-1 text-lg font-semibold text-text-primary'
            }
          >
            {c.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}
