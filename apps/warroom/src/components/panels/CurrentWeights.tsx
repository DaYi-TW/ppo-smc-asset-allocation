/**
 * CurrentWeights — sidebar 顯示「最新 frame 的當前配置」by bucket。
 *
 * 對應 mockup `.agent-card`「當前配置權重」：
 *   攻擊型 (Risk-On) · 52%
 *     NVDA  ▓▓▓▓▓▓░░░░  22%
 *     AMD   ▓▓▓▓░░░░░░  14%
 *     ...
 *   避險型 (Risk-Off) · 36%
 *     GLD   ▓▓▓▓▓░░░░░  21%
 *     TLT   ▓▓▓▓░░░░░░  15%
 *   現金 (Cash) · 12%
 *     CASH  ▓▓▓░░░░░░░  12%
 *
 * Bar 寬度 = 該資產佔該 bucket 的比例（不是佔全 portfolio），保留 mockup 視覺。
 */

import { useTranslation } from 'react-i18next'

import { formatPercent } from '@/utils/format'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

const RISK_ON = ['NVDA', 'AMD', 'TSM', 'MU'] as const
const RISK_OFF = ['GLD', 'TLT'] as const

export interface CurrentWeightsProps {
  frame: TrajectoryFrame
}

interface Bucket {
  label: string
  total: number
  members: ReadonlyArray<{ name: string; weight: number }>
  color: string
}

export function CurrentWeights({ frame }: CurrentWeightsProps) {
  const { t } = useTranslation()

  const buckets: Bucket[] = [
    {
      label: t('overview.weightChart.legend.riskOn'),
      total: frame.weights.riskOn,
      members: RISK_ON.map((a) => ({ name: a, weight: frame.weights.perAsset[a] ?? 0 })),
      color: 'bg-warn',
    },
    {
      label: t('overview.weightChart.legend.riskOff'),
      total: frame.weights.riskOff,
      members: RISK_OFF.map((a) => ({ name: a, weight: frame.weights.perAsset[a] ?? 0 })),
      color: 'bg-success',
    },
    {
      label: t('overview.weightChart.legend.cash'),
      total: frame.weights.cash,
      members: [{ name: 'CASH', weight: frame.weights.cash }],
      color: 'bg-text-muted',
    },
  ]

  return (
    <div className="flex flex-col gap-3" aria-label={t('overview.weightChart.title')}>
      {buckets.map((b) => (
        <div key={b.label} className="flex flex-col gap-1.5">
          <div className="text-[11px] uppercase tracking-wider text-text-muted">
            {b.label} ·{' '}
            <span className="text-text-secondary">
              {formatPercent(b.total, { fractionDigits: 0, signDisplay: 'never' })}
            </span>
          </div>
          {b.members.map((m) => {
            const widthPct = b.total > 0 ? (m.weight / b.total) * 100 : 0
            return (
              <div
                key={m.name}
                className="grid grid-cols-[60px_minmax(0,1fr)_50px] items-center gap-2 text-xs"
              >
                <span className="font-mono font-semibold text-text-primary">{m.name}</span>
                <div className="h-1.5 overflow-hidden rounded bg-bg-base">
                  <div
                    className={`h-full ${b.color}`}
                    style={{ width: `${Math.min(100, widthPct)}%` }}
                  />
                </div>
                <span className="text-right font-mono text-text-secondary">
                  {formatPercent(m.weight, { fractionDigits: 0, signDisplay: 'never' })}
                </span>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
