/**
 * KPIRow — 戰情總覽頂部 5 卡，對齊 mockup `.kpi-row`：
 *
 *   ┌─ LABEL (uppercase, sm) ──┐
 *   │ VALUE (clamp 18-26px)    │
 *   │ delta (xs)               │
 *   └──────────────────────────┘
 *
 * 5 卡：投組淨值、累計報酬、Sharpe、最大回撤、當期動作熵。
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { formatNumber, formatPercent, formatUSD } from '@/utils/format'
import type { EpisodeSummaryViewModel } from '@/viewmodels/episode'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface KPIRowProps {
  episode: EpisodeSummaryViewModel
  frames: ReadonlyArray<TrajectoryFrame>
}

interface Card {
  label: string
  value: string
  delta?: string | undefined
  valueTone?: 'default' | 'positive' | 'negative' | undefined
  deltaTone?: 'default' | 'positive' | 'negative' | undefined
}

function meanEntropy(frames: ReadonlyArray<TrajectoryFrame>): number {
  if (frames.length === 0) return Number.NaN
  let sum = 0
  let n = 0
  for (const f of frames) {
    if (Number.isFinite(f.action.entropy)) {
      sum += f.action.entropy
      n += 1
    }
  }
  return n > 0 ? sum / n : Number.NaN
}

export function KPIRow({ episode, frames }: KPIRowProps) {
  const { t } = useTranslation()

  const last = frames[frames.length - 1]
  const prev = frames[frames.length - 2]

  const cards = useMemo<Card[]>(() => {
    const navValue = last?.nav ?? Number.NaN
    const navDeltaAbs = last && prev ? last.nav - prev.nav : 0
    const navDeltaPct = last && prev && prev.nav > 0 ? (last.nav - prev.nav) / prev.nav : 0
    const entropy = meanEntropy(frames)

    return [
      {
        label: t('overview.kpi.nav'),
        value: Number.isFinite(navValue) ? formatUSD(navValue, { fractionDigits: 0 }) : '—',
        delta:
          last && prev
            ? `${formatNumber(navDeltaAbs, { fractionDigits: 0, signDisplay: 'always' })} (${formatPercent(navDeltaPct, { fractionDigits: 2 })}) 本日`
            : undefined,
        deltaTone: navDeltaAbs >= 0 ? 'positive' : 'negative',
      },
      {
        label: t('overview.summary.totalReturn'),
        value: formatPercent(episode.totalReturn, { fractionDigits: 2 }),
        delta: `${t('overview.kpi.startedAt', { date: episode.startDate })}`,
        valueTone: episode.totalReturn >= 0 ? 'positive' : 'negative',
      },
      {
        label: t('overview.summary.sharpeRatio'),
        value: formatNumber(episode.sharpeRatio, { fractionDigits: 2 }),
        delta: t('overview.kpi.riskFree'),
      },
      {
        label: t('overview.summary.maxDrawdown'),
        value: formatPercent(episode.maxDrawdown, { fractionDigits: 2 }),
        valueTone: 'negative',
        delta: t('overview.kpi.mddHint'),
      },
      {
        label: t('overview.kpi.entropy'),
        value: formatNumber(entropy, { fractionDigits: 3 }),
        delta: t('overview.kpi.entropyHint'),
      },
    ]
  }, [episode, frames, last, prev, t])

  return (
    <dl
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      aria-label={t('overview.kpi.label')}
    >
      {cards.map((c) => (
        <div
          key={c.label}
          className="rounded-xl border border-border bg-bg-surface px-4 py-3.5 shadow-sm"
        >
          <dt className="truncate text-[11px] font-medium uppercase tracking-wider text-text-secondary">
            {c.label}
          </dt>
          <dd
            className={
              c.valueTone === 'positive'
                ? 'mt-1.5 text-[clamp(18px,2.4vw,26px)] font-bold leading-tight text-success'
                : c.valueTone === 'negative'
                  ? 'mt-1.5 text-[clamp(18px,2.4vw,26px)] font-bold leading-tight text-danger'
                  : 'mt-1.5 text-[clamp(18px,2.4vw,26px)] font-bold leading-tight text-text-primary'
            }
          >
            {c.value}
          </dd>
          {c.delta && (
            <p
              className={
                c.deltaTone === 'positive'
                  ? 'mt-1 text-xs text-success'
                  : c.deltaTone === 'negative'
                    ? 'mt-1 text-xs text-danger'
                    : 'mt-1 text-xs text-text-secondary'
              }
            >
              {c.delta}
            </p>
          )}
        </div>
      ))}
    </dl>
  )
}
