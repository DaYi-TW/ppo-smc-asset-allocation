/**
 * WeightStackedArea — 3-bucket 權重 stacked area chart（對齊 mockup `chart-alloc`）。
 *
 * 三層：Risk-On / Risk-Off / Cash，色彩沿用 mockup 之 orange / green / slate。
 * 視覺上比 7-asset stack 乾淨，且與 sidebar `CurrentWeights` 的 bucket 分組一致。
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
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

const RISK_ON_COLOR = '#f97316' // orange-500
const RISK_OFF_COLOR = '#22c55e' // green-500
const CASH_COLOR = '#94a3b8' // slate-400

export interface WeightStackedAreaProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
}

interface BucketPoint {
  timestamp: string
  riskOn: number
  riskOff: number
  cash: number
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

  const data = useMemo<BucketPoint[]>(
    () =>
      frames.map((f) => ({
        timestamp: f.timestamp,
        riskOn: f.weights.riskOn,
        riskOff: f.weights.riskOff,
        cash: f.weights.cash,
      })),
    [frames],
  )

  return (
    <div
      role="figure"
      aria-label={t('overview.weightChart.title')}
      style={{ width: '100%', height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={theme.grid}
            vertical={false}
          />
          <XAxis
            dataKey="timestamp"
            stroke={theme.text}
            tick={{ fontSize: 11, fill: theme.text }}
            tickFormatter={(v: string) => v.slice(0, 10)}
            minTickGap={48}
          />
          <YAxis
            stroke={theme.text}
            tick={{ fontSize: 11, fill: theme.text }}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            domain={[0, 1]}
          />
          <Tooltip
            contentStyle={{
              background: theme.background,
              border: `1px solid ${theme.border}`,
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: theme.text }}
            formatter={(value: number, name: string) => [
              formatPercent(value, { fractionDigits: 1, signDisplay: 'never' }),
              name,
            ]}
          />
          <Legend
            wrapperStyle={{ color: theme.text, fontSize: 11, paddingTop: 4 }}
            iconType="square"
          />
          <Area
            type="monotone"
            dataKey="riskOn"
            name={t('overview.weightChart.legend.riskOn')}
            stackId="weights"
            stroke={RISK_ON_COLOR}
            fill={RISK_ON_COLOR}
            fillOpacity={0.7}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="riskOff"
            name={t('overview.weightChart.legend.riskOff')}
            stackId="weights"
            stroke={RISK_OFF_COLOR}
            fill={RISK_OFF_COLOR}
            fillOpacity={0.7}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="cash"
            name={t('overview.weightChart.legend.cash')}
            stackId="weights"
            stroke={CASH_COLOR}
            fill={CASH_COLOR}
            fillOpacity={0.7}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
