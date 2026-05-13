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

import { useInitialCapital } from '@/contexts/InitialCapitalContext'
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
  const initialCapital = useInitialCapital()

  const first = frames[0]
  const last = frames[frames.length - 1]

  const cards = useMemo<Card[]>(() => {
    // NAV 後端是「報酬率單位」（起始 1.0）；前端按使用者設定的 initialCapital 乘成
    // 「美金面值」顯示。預設 1 時保持原樣，預設 100000 時呈現本金→現值。
    //
    // 「投組淨值」主值 = 視窗末端 NAV（= 右把手 = 現值）；
    // delta = 起點 → 末端 累計，加上「自 {進場日}」標示左把手日期。
    const navValue = last ? last.nav * initialCapital : Number.NaN
    const hasWindow = !!(first && last && first !== last)
    const navDeltaAbs = hasWindow ? (last!.nav - first!.nav) * initialCapital : 0
    const navDeltaPct = hasWindow && first!.nav > 0 ? last!.nav / first!.nav - 1 : 0
    const entryDate = first?.timestamp.slice(0, 10)
    const entropy = meanEntropy(frames)
    // NAV 小於 100 時是「報酬率單位」（起始 1.0），整數位看不出變化 → 顯示 4 位小數。
    // 大於等於 100 時是「美金本金」（initial_capital=100000 之類），維持 0 位。
    const navFractionDigits = Number.isFinite(navValue) && navValue < 100 ? 4 : 0

    return [
      {
        label: t('overview.kpi.nav'),
        value: Number.isFinite(navValue)
          ? formatUSD(navValue, { fractionDigits: navFractionDigits })
          : '—',
        delta: hasWindow
          ? `自 ${entryDate} ${formatNumber(navDeltaAbs, { fractionDigits: navFractionDigits, signDisplay: 'always' })} (${formatPercent(navDeltaPct, { fractionDigits: 2 })})`
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
  }, [episode, frames, first, last, t, initialCapital])

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
