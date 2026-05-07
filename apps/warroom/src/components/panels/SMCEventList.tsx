/**
 * SMCEventList — sidebar 顯示「最近 N 次非 neutral 的 SMC 訊號」。
 *
 * 對應 mockup `.events`：60px tag + body + meta（multi-line）。
 * 從 frames 倒序掃描，取出 bos/choch ≠ 0、obTouching=true、|fvgDistancePct|<=2% 的事件。
 * 注意：CSV-only fixture 不含 SMC（全 0），這時會顯示 EmptyState。
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { formatDate, formatPercent } from '@/utils/format'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface SMCEventListProps {
  frames: ReadonlyArray<TrajectoryFrame>
  /** 最多顯示幾筆，預設 5（與 mockup 對齊）。 */
  limit?: number
}

type EventKind = 'BOS' | 'CHOCH' | 'FVG' | 'OB'

interface Event {
  step: number
  date: string
  kind: EventKind
  title: string
  meta: string
}

const TAG_STYLE: Record<EventKind, string> = {
  BOS: 'bg-success/15 text-success border-success/40',
  CHOCH: 'bg-danger/15 text-danger border-danger/40',
  FVG: 'bg-info/15 text-info border-info/40',
  OB: 'bg-warn/15 text-warn border-warn/40',
}

export function SMCEventList({ frames, limit = 5 }: SMCEventListProps) {
  const { t } = useTranslation()

  const events = useMemo<Event[]>(() => {
    const out: Event[] = []
    for (let i = frames.length - 1; i >= 0 && out.length < limit; i -= 1) {
      const f = frames[i]
      if (!f) continue
      const close = f.ohlcv.close
      if (f.smcSignals.bos !== 0) {
        out.push({
          step: f.step,
          date: f.timestamp,
          kind: 'BOS',
          title: f.smcSignals.bos === 1 ? `突破 swing high @ ${close.toFixed(2)}` : `跌破 swing low @ ${close.toFixed(2)}`,
          meta: f.smcSignals.bos === 1 ? '趨勢延續確認' : '趨勢反轉訊號',
        })
        if (out.length >= limit) break
      }
      if (f.smcSignals.choch !== 0) {
        out.push({
          step: f.step,
          date: f.timestamp,
          kind: 'CHOCH',
          title: f.smcSignals.choch === 1 ? `bullish CHoCh @ ${close.toFixed(2)}` : `bearish CHoCh @ ${close.toFixed(2)}`,
          meta: f.smcSignals.choch === 1 ? '結構轉多' : '結構轉空',
        })
        if (out.length >= limit) break
      }
      if (Number.isFinite(f.smcSignals.fvgDistancePct) && Math.abs(f.smcSignals.fvgDistancePct) <= 0.02 && f.smcSignals.fvgDistancePct !== 0) {
        out.push({
          step: f.step,
          date: f.timestamp,
          kind: 'FVG',
          title: `FVG distance ${formatPercent(f.smcSignals.fvgDistancePct, { fractionDigits: 2 })}`,
          meta: 'unfilled gap 接近',
        })
        if (out.length >= limit) break
      }
      if (f.smcSignals.obTouching) {
        out.push({
          step: f.step,
          date: f.timestamp,
          kind: 'OB',
          title: `觸碰 OB @ ${close.toFixed(2)}`,
          meta: `distance ratio ${f.smcSignals.obDistanceRatio.toFixed(2)} ATR`,
        })
      }
    }
    return out.slice(0, limit)
  }, [frames, limit])

  if (events.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        {t('overview.smc.empty')}
      </p>
    )
  }

  return (
    <ul
      className="flex flex-col divide-y divide-border"
      aria-label={t('overview.smc.title')}
    >
      {events.map((e, idx) => (
        <li
          key={`${e.step}-${e.kind}-${idx}`}
          className="grid grid-cols-[60px_minmax(0,1fr)] gap-2 py-2.5 text-xs"
        >
          <span
            className={`self-start rounded border px-1.5 py-0.5 text-center text-[10px] font-semibold ${TAG_STYLE[e.kind]}`}
          >
            {e.kind === 'CHOCH' ? 'CHoCh' : e.kind}
          </span>
          <div className="break-words text-text-primary">
            {e.title}
            <div className="mt-0.5 text-[11px] text-text-muted">
              {formatDate(e.date)} · #{e.step} · {e.meta}
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}
