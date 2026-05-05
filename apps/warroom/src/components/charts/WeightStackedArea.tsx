/**
 * WeightStackedArea — 7 維 per-asset 權重 stacked area chart。
 *
 * Recharts 不支援 CSS variable，主題切換時 component 透過 useEffect 重讀
 * getChartTheme() 並觸發 re-render。
 */

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { getChartTheme, type ChartTheme } from '@/theme/getChartTheme'
import { formatPercent } from '@/utils/format'
import { buildWeightStackPoints } from '@/utils/chart-helpers'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

const ASSET_ORDER = ['CASH', 'TLT', 'GLD', 'MU', 'TSM', 'AMD', 'NVDA'] as const

export interface WeightStackedAreaProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
}

export function WeightStackedArea({ frames, height = 320 }: WeightStackedAreaProps) {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<ChartTheme>(() => getChartTheme())

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setTheme(getChartTheme()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  const data = useMemo(() => buildWeightStackPoints(frames), [frames])

  return (
    <div
      role="figure"
      aria-label={t('overview.weightChart.title')}
      style={{ width: '100%', height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="timestamp" stroke={theme.text} tick={{ fontSize: 12 }} />
          <YAxis
            stroke={theme.text}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => formatPercent(v, { fractionDigits: 0, signDisplay: 'never' })}
            domain={[0, 1]}
          />
          <Tooltip
            contentStyle={{ background: theme.background, border: `1px solid ${theme.border}` }}
            formatter={(value: number, name: string) => [
              formatPercent(value, { fractionDigits: 1, signDisplay: 'never' }),
              name,
            ]}
            labelStyle={{ color: theme.text }}
          />
          <Legend wrapperStyle={{ color: theme.text }} />
          {ASSET_ORDER.map((asset) => (
            <Area
              key={asset}
              type="monotone"
              dataKey={asset}
              stackId="weights"
              stroke={theme.asset[asset]}
              fill={theme.asset[asset]}
              fillOpacity={0.7}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
