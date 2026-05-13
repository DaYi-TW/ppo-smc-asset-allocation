/**
 * NavDrawdownChart — 雙軸 ComposedChart：
 *   - 左軸：NAV (USD) line
 *   - 右軸：drawdown% area（紅色，0 為頂、向下延伸）
 *
 * drawdown 從 frame.drawdownPct 取（後端已算）；若不存在則由 computeDrawdownSeries fallback。
 */

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useInitialCapital } from '@/contexts/InitialCapitalContext'
import { getChartTheme, type ChartTheme } from '@/theme/getChartTheme'
import { computeDrawdownSeries } from '@/utils/chart-helpers'
import { formatPercent, formatUSD } from '@/utils/format'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface NavDrawdownChartProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
}

interface ChartPoint {
  timestamp: string
  nav: number
  drawdownPct: number
}

export function NavDrawdownChart({ frames, height = 320 }: NavDrawdownChartProps) {
  const { t } = useTranslation()
  const initialCapital = useInitialCapital()
  const [theme, setTheme] = useState<ChartTheme>(() => getChartTheme())

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setTheme(getChartTheme()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  const data = useMemo<ChartPoint[]>(() => {
    const fallback = computeDrawdownSeries(frames)
    return frames.map((f, i) => ({
      timestamp: f.timestamp,
      nav: f.nav * initialCapital,
      drawdownPct: f.drawdownPct ?? fallback[i]?.drawdownPct ?? 0,
    }))
  }, [frames, initialCapital])

  // tickFormatter / Tooltip 顯示時用相同規則：< 100 顯示 4 位小數
  const navFractionDigits = initialCapital < 100 ? 4 : 0

  return (
    <div
      role="figure"
      aria-label={t('overview.navChart.title')}
      style={{ width: '100%', height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="timestamp" stroke={theme.text} tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="nav"
            stroke={theme.text}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => formatUSD(v, { fractionDigits: navFractionDigits })}
            label={{
              value: t('overview.navChart.navAxis'),
              angle: -90,
              position: 'insideLeft',
              fill: theme.text,
              fontSize: 12,
            }}
          />
          <YAxis
            yAxisId="drawdown"
            orientation="right"
            stroke={theme.danger}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => formatPercent(v, { fractionDigits: 0, signDisplay: 'never' })}
            domain={[(min: number) => Math.min(min, -0.05), 0]}
            label={{
              value: t('overview.navChart.drawdownAxis'),
              angle: 90,
              position: 'insideRight',
              fill: theme.danger,
              fontSize: 12,
            }}
          />
          <Tooltip
            contentStyle={{ background: theme.background, border: `1px solid ${theme.border}` }}
            labelStyle={{ color: theme.text }}
            formatter={(value: number, name: string) => {
              if (name === 'NAV')
                return [formatUSD(value, { fractionDigits: navFractionDigits }), name]
              return [formatPercent(value, { fractionDigits: 2 }), name]
            }}
          />
          <Legend wrapperStyle={{ color: theme.text }} />
          <Area
            yAxisId="drawdown"
            type="monotone"
            dataKey="drawdownPct"
            name="Drawdown"
            stroke={theme.danger}
            fill={theme.danger}
            fillOpacity={0.2}
            isAnimationActive={false}
          />
          <Line
            yAxisId="nav"
            type="monotone"
            dataKey="nav"
            name="NAV"
            stroke={theme.navLine}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
