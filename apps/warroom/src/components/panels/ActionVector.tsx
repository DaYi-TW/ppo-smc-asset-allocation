/**
 * ActionVector — 顯示 PPO action：raw vs normalized vs log-prob/entropy。
 */

import { useTranslation } from 'react-i18next'

import { formatNumber } from '@/utils/format'
import type { ActionVector as ActionVectorVM } from '@/viewmodels/trajectory'

const ASSETS = ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT', 'CASH'] as const

export interface ActionVectorProps {
  action: ActionVectorVM
}

export function ActionVector({ action }: ActionVectorProps) {
  const { t } = useTranslation()
  const dim = Math.max(action.raw.length, action.normalized.length, ASSETS.length)

  return (
    <section
      aria-label={t('decision.action.title')}
      className="flex flex-col gap-sm"
    >
      <div className="flex flex-wrap gap-md text-xs text-text-secondary">
        <span>{t('decision.action.logProb', { value: formatNumber(action.logProb, { fractionDigits: 3 }) })}</span>
        <span>{t('decision.action.entropy', { value: formatNumber(action.entropy, { fractionDigits: 3 }) })}</span>
      </div>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-secondary">
            <th className="py-1 pr-3">Asset</th>
            <th className="py-1 pr-3">raw</th>
            <th className="py-1">normalized</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: dim }).map((_, i) => {
            const asset = ASSETS[i] ?? `dim${i}`
            const raw = action.raw[i] ?? Number.NaN
            const norm = action.normalized[i] ?? Number.NaN
            return (
              <tr key={asset} className="border-b border-border/60 last:border-0">
                <td className="py-1 pr-3 font-mono text-xs text-text-primary">{asset}</td>
                <td className="py-1 pr-3 font-mono text-xs text-text-primary">
                  {formatNumber(raw, { fractionDigits: 4 })}
                </td>
                <td className="py-1 font-mono text-xs text-text-secondary">
                  {formatNumber(norm, { fractionDigits: 4 })}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
