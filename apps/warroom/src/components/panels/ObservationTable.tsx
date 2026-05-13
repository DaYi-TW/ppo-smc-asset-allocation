/**
 * ObservationTable — 顯示單一 frame 的觀測值（feature / value / normalized）。
 *
 * 觀測來源：將 frame.weights.perAsset + smcSignals 攤平為 row list。
 * （後端正式 obs vector 較複雜；本檔次以可解釋欄位呈現給審查者。）
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { useInitialCapital } from '@/contexts/InitialCapitalContext'
import { formatNumber, formatPercent } from '@/utils/format'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface ObservationTableProps {
  frame: TrajectoryFrame
}

interface Row {
  feature: string
  value: string
  normalized: string
}

export function ObservationTable({ frame }: ObservationTableProps) {
  const { t } = useTranslation()
  const initialCapital = useInitialCapital()

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = []
    const navDisplay = frame.nav * initialCapital
    const navFractionDigits = navDisplay < 100 ? 4 : 0
    out.push({
      feature: 'NAV',
      value: formatNumber(navDisplay, { fractionDigits: navFractionDigits }),
      normalized: formatNumber(frame.nav, { fractionDigits: 4 }),
    })
    out.push({
      feature: 'Drawdown',
      value: formatPercent(frame.drawdownPct, { fractionDigits: 2 }),
      normalized: formatNumber(frame.drawdownPct, { fractionDigits: 4 }),
    })
    for (const [asset, weight] of Object.entries(frame.weights.perAsset)) {
      out.push({
        feature: `weight.${asset}`,
        value: formatPercent(weight, { fractionDigits: 1, signDisplay: 'never' }),
        normalized: formatNumber(weight, { fractionDigits: 4 }),
      })
    }
    out.push({
      feature: 'smc.bos',
      value: String(frame.smcSignals.bos),
      normalized: String(frame.smcSignals.bos),
    })
    out.push({
      feature: 'smc.choch',
      value: String(frame.smcSignals.choch),
      normalized: String(frame.smcSignals.choch),
    })
    out.push({
      feature: 'smc.fvgDistancePct',
      value: Number.isFinite(frame.smcSignals.fvgDistancePct)
        ? formatPercent(frame.smcSignals.fvgDistancePct, { fractionDigits: 2 })
        : '—',
      normalized: formatNumber(frame.smcSignals.fvgDistancePct, { fractionDigits: 4 }),
    })
    out.push({
      feature: 'smc.obTouching',
      value: frame.smcSignals.obTouching ? '1' : '0',
      normalized: frame.smcSignals.obTouching ? '1' : '0',
    })
    out.push({
      feature: 'smc.obDistanceRatio',
      value: Number.isFinite(frame.smcSignals.obDistanceRatio)
        ? formatNumber(frame.smcSignals.obDistanceRatio, { fractionDigits: 3 })
        : '—',
      normalized: formatNumber(frame.smcSignals.obDistanceRatio, { fractionDigits: 4 }),
    })
    return out
  }, [frame, initialCapital])

  return (
    <table className="w-full border-collapse text-sm" aria-label={t('decision.observation.title')}>
      <thead>
        <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-secondary">
          <th className="py-1 pr-3">{t('decision.observation.col.feature')}</th>
          <th className="py-1 pr-3">{t('decision.observation.col.value')}</th>
          <th className="py-1">{t('decision.observation.col.normalized')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.feature} className="border-b border-border/60 last:border-0">
            <td className="py-1 pr-3 font-mono text-xs text-text-primary">{r.feature}</td>
            <td className="py-1 pr-3 text-text-primary">{r.value}</td>
            <td className="py-1 font-mono text-xs text-text-secondary">{r.normalized}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
