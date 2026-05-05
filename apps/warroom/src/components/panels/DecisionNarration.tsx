/**
 * DecisionNarration — 用 i18n template 從 frame 生成自然語言描述。
 *
 * 規則：選 normalized 權重最大的 asset 作為主動作；rationale 由 SMC 訊號 + drawdown 推導。
 */

import { useTranslation } from 'react-i18next'

import { formatDate, formatPercent } from '@/utils/format'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface DecisionNarrationProps {
  frame: TrajectoryFrame
}

const ASSETS = ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT', 'CASH'] as const

function pickTopAsset(perAsset: Record<string, number>): { asset: string; weight: number } {
  let topAsset = ASSETS[0] as string
  let topWeight = -Infinity
  for (const [a, w] of Object.entries(perAsset)) {
    if (w > topWeight) {
      topWeight = w
      topAsset = a
    }
  }
  return { asset: topAsset, weight: topWeight }
}

function deriveRationale(frame: TrajectoryFrame, t: (k: string) => string): string {
  const { smcSignals: s, drawdownPct } = frame
  const parts: string[] = []
  if (s.bos === 1) parts.push('BOS↑')
  if (s.bos === -1) parts.push('BOS↓')
  if (s.choch === 1) parts.push('CHoCh↑')
  if (s.choch === -1) parts.push('CHoCh↓')
  if (s.obTouching) parts.push('OB-touch')
  if (drawdownPct < -0.05) parts.push(`MDD ${formatPercent(drawdownPct, { fractionDigits: 1 })}`)
  if (parts.length === 0) parts.push(t('overview.summary.totalReturn'))
  return parts.join(' · ')
}

export function DecisionNarration({ frame }: DecisionNarrationProps) {
  const { t } = useTranslation()
  const { asset, weight } = pickTopAsset(frame.weights.perAsset)
  const text = t('decision.narration.template', {
    date: formatDate(frame.timestamp),
    action: `${asset} ${formatPercent(weight, { fractionDigits: 1, signDisplay: 'never' })}`,
    rationale: deriveRationale(frame, t),
  })
  return (
    <p className="rounded border-l-4 border-primary bg-bg-surface p-md text-sm text-text-primary">
      {text}
    </p>
  )
}
