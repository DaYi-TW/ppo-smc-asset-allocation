/**
 * RewardBreakdown — 視覺化 reward 三項分量（return - drawdownPenalty - costPenalty = total）。
 *
 * 雙呈現：
 *   - 單步 stacked bar：顯示當前 step 的三項分量。
 *   - 累積 line chart：顯示三項分量的累積曲線（與 frame.step 對齊）。
 *
 * 對應憲法 III「風險優先獎勵」：penalty 必須以負值顯示給審查者看到 trade-off。
 */

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { getChartTheme, type ChartTheme } from '@/theme/getChartTheme'
import { formatNumber } from '@/utils/format'
import type { RewardSeries } from '@/viewmodels/reward'

export interface RewardBreakdownProps {
  series: RewardSeries
  /** 如果指定了 step，stacked bar 會聚焦在該 step；否則用最後一筆。 */
  step?: number
  height?: number
}

export function RewardBreakdown({ series, step, height = 240 }: RewardBreakdownProps) {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<ChartTheme>(() => getChartTheme())

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setTheme(getChartTheme()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  const focusStep = step ?? series.byStep.length - 1
  const snapshot = series.byStep[focusStep] ?? series.byStep.at(-1)

  const stackData = useMemo(() => {
    if (!snapshot) return []
    return [
      {
        label: t('decision.reward.return'),
        return: snapshot.returnComponent,
        drawdownPenalty: -snapshot.drawdownPenalty,
        costPenalty: -snapshot.costPenalty,
      },
    ]
  }, [snapshot, t])

  const cumulativeData = useMemo(
    () =>
      series.cumulative.map((p) => ({
        step: p.step,
        return: p.cumulativeReturn,
        drawdownPenalty: -p.cumulativeDrawdownPenalty,
        costPenalty: -p.cumulativeCostPenalty,
        total: p.cumulativeTotal,
      })),
    [series.cumulative],
  )

  return (
    <div
      role="figure"
      aria-label={t('decision.reward.title')}
      className="flex flex-col gap-md"
    >
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={stackData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
            <XAxis dataKey="label" stroke={theme.text} />
            <YAxis
              stroke={theme.text}
              tickFormatter={(v: number) => formatNumber(v, { fractionDigits: 3 })}
            />
            <Tooltip
              contentStyle={{ background: theme.background, border: `1px solid ${theme.border}` }}
              labelStyle={{ color: theme.text }}
              formatter={(v: number, name: string) => [formatNumber(v, { fractionDigits: 4 }), name]}
            />
            <Legend wrapperStyle={{ color: theme.text }} />
            <Bar
              stackId="reward"
              dataKey="return"
              name={t('decision.reward.return')}
              fill={theme.success}
              isAnimationActive={false}
            />
            <Bar
              stackId="reward"
              dataKey="drawdownPenalty"
              name={t('decision.reward.drawdownPenalty')}
              fill={theme.danger}
              isAnimationActive={false}
            />
            <Bar
              stackId="reward"
              dataKey="costPenalty"
              name={t('decision.reward.costPenalty')}
              fill={theme.primary}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={cumulativeData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
            <XAxis dataKey="step" stroke={theme.text} tick={{ fontSize: 12 }} />
            <YAxis
              stroke={theme.text}
              tick={{ fontSize: 12 }}
              tickFormatter={(v: number) => formatNumber(v, { fractionDigits: 2 })}
            />
            <Tooltip
              contentStyle={{ background: theme.background, border: `1px solid ${theme.border}` }}
              labelStyle={{ color: theme.text }}
              formatter={(v: number, name: string) => [formatNumber(v, { fractionDigits: 3 }), name]}
            />
            <Legend wrapperStyle={{ color: theme.text }} />
            <Line
              type="monotone"
              dataKey="return"
              name={t('decision.reward.return')}
              stroke={theme.success}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="drawdownPenalty"
              name={t('decision.reward.drawdownPenalty')}
              stroke={theme.danger}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="costPenalty"
              name={t('decision.reward.costPenalty')}
              stroke={theme.primary}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="total"
              name={t('decision.reward.total')}
              stroke={theme.navLine}
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
