/**
 * RewardSidebar — 對應 mockup 「Reward 拆解（最近 step）」卡片。
 *
 * 三條 reward 分量 bar + Net reward 行；視覺上 mockup style：
 *   階段報酬   +0.0123   ▓▓▓▓▓▓▓▓▓▓░░░░░░ (62%)
 *   MDD 懲罰   -0.0028   ▓▓░░░░░░░░░░░░░░ (14%)
 *   交易成本   -0.0015   ▓░░░░░░░░░░░░░░░ ( 8%)
 *   ───────────────────────────────
 *   Net reward                  +0.0080
 *
 * 寬度 % = abs(component) / max(abs(...)) * 100，避免單側壓縮。
 */

import { useTranslation } from 'react-i18next'

import { formatNumber } from '@/utils/format'
import type { RewardSnapshot } from '@/viewmodels/reward'

export interface RewardSidebarProps {
  reward: RewardSnapshot
}

export function RewardSidebar({ reward }: RewardSidebarProps) {
  const { t } = useTranslation()

  const items = [
    {
      key: 'return' as const,
      label: t('decision.reward.return'),
      value: reward.returnComponent,
      color: 'bg-success',
    },
    {
      key: 'dd' as const,
      label: t('decision.reward.drawdownPenalty'),
      value: -reward.drawdownPenalty,
      color: 'bg-danger',
    },
    {
      key: 'cost' as const,
      label: t('decision.reward.costPenalty'),
      value: -reward.costPenalty,
      color: 'bg-warn',
    },
  ]

  const maxAbs = items.reduce((m, it) => Math.max(m, Math.abs(it.value)), 1e-9)
  const net = reward.total

  return (
    <div className="flex flex-col gap-3" aria-label={t('decision.reward.title')}>
      {items.map((it) => {
        const widthPct = Math.min(100, (Math.abs(it.value) / maxAbs) * 100)
        return (
          <div key={it.key} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-text-primary">{it.label}</span>
              <span className="font-mono text-text-secondary">
                {formatNumber(it.value, { fractionDigits: 4, signDisplay: 'always' })}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded bg-bg-base">
              <div
                className={`h-full ${it.color}`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </div>
        )
      })}

      <div className="mt-1 flex items-baseline justify-between border-t border-border pt-2 text-xs">
        <span className="text-text-secondary">{t('decision.reward.total')}</span>
        <span
          className={`font-mono font-semibold ${net >= 0 ? 'text-success' : 'text-danger'}`}
        >
          {formatNumber(net, { fractionDigits: 4, signDisplay: 'always' })}
        </span>
      </div>
    </div>
  )
}
