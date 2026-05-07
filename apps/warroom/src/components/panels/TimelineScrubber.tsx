/**
 * TimelineScrubber — 全域時間軸拖動條。
 *
 * 視覺：一條全寬 NAV mini-area chart，疊上 Recharts Brush（雙把手）。
 * 拖動時把 [startIndex, endIndex] 推給 TimeRangeContext，所有圖表同步更新。
 *
 * 為什麼用 Recharts Brush：
 *  - 內建雙把手 + 中央可拖整段
 *  - 自動跟 chart x 軸對齊
 *  - 已有 Recharts dep，不額外引 lib
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Area, AreaChart, Brush, ResponsiveContainer, YAxis } from 'recharts'

import { useTimeRange } from '@/contexts/TimeRangeContext'
import { getChartTheme, type ChartTheme } from '@/theme/getChartTheme'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface TimelineScrubberProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
}

interface NavPoint {
  index: number
  timestamp: string
  nav: number
}

export function TimelineScrubber({ frames, height = 64 }: TimelineScrubberProps) {
  const { t } = useTranslation()
  const { range, setRange } = useTimeRange(frames.length)
  const [theme, setTheme] = useState<ChartTheme>(() => getChartTheme())
  // Brush 是 uncontrolled — 用 key 強制重置（換 episode、reset 按鈕時）
  const [brushKey, setBrushKey] = useState(0)
  const lastEmittedRef = useRef<{ start: number; end: number }>({
    start: range.start,
    end: range.end,
  })

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setTheme(getChartTheme()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  const data = useMemo<NavPoint[]>(
    () =>
      frames.map((f, i) => ({
        index: i,
        timestamp: f.timestamp,
        nav: f.nav,
      })),
    [frames],
  )

  const total = frames.length
  // Brush 用 inclusive index，context 用 slice-style end (exclusive)
  const brushStart = Math.min(range.start, Math.max(0, total - 1))
  const brushEnd = Math.min(Math.max(range.end - 1, brushStart), Math.max(0, total - 1))

  const handleBrushChange = ({
    startIndex,
    endIndex,
  }: {
    startIndex?: number
    endIndex?: number
  }) => {
    if (startIndex == null || endIndex == null) return
    const nextStart = startIndex
    const nextEnd = endIndex + 1 // exclusive
    if (
      lastEmittedRef.current.start === nextStart &&
      lastEmittedRef.current.end === nextEnd
    ) {
      return
    }
    lastEmittedRef.current = { start: nextStart, end: nextEnd }
    setRange({ start: nextStart, end: nextEnd })
  }

  const handleReset = () => {
    setRange({ start: 0, end: total })
    setBrushKey((k) => k + 1)
  }

  const startLabel = frames[brushStart]?.timestamp.slice(0, 10) ?? '—'
  const endLabel = frames[brushEnd]?.timestamp.slice(0, 10) ?? '—'
  const isFullRange = brushStart === 0 && brushEnd === total - 1
  const windowSize = brushEnd - brushStart + 1

  if (total === 0) return null

  return (
    <div
      className="rounded-xl border border-border bg-bg-surface p-3"
      aria-label={t('overview.timeline.label')}
    >
      <div className="mb-1 flex items-center justify-between text-[11px] text-text-secondary">
        <span>
          <span className="font-mono text-text-primary">{startLabel}</span>
          <span className="mx-1.5 text-text-muted">→</span>
          <span className="font-mono text-text-primary">{endLabel}</span>
          <span className="ml-2 text-text-muted">
            ({t('overview.timeline.windowSize', { count: windowSize })})
          </span>
        </span>
        <button
          type="button"
          onClick={handleReset}
          disabled={isFullRange}
          className="rounded border border-border bg-bg-elevated px-2 py-0.5 text-[11px] text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t('overview.timeline.reset')}
        </button>
      </div>
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
            <YAxis hide domain={['auto', 'auto']} />
            <Area
              type="monotone"
              dataKey="nav"
              stroke={theme.info}
              fill={theme.info}
              fillOpacity={0.18}
              strokeWidth={1}
              isAnimationActive={false}
            />
            <Brush
              key={brushKey}
              dataKey="timestamp"
              height={20}
              stroke={theme.info}
              fill={theme.background}
              travellerWidth={8}
              startIndex={brushStart}
              endIndex={brushEnd}
              onChange={handleBrushChange}
              tickFormatter={() => ''}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
