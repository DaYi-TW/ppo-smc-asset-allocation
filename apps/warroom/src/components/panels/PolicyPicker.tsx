/**
 * PolicyPicker — 顯示可用的 PPO policies 並切換當前策略。
 *
 * - 載入中顯示 skeleton；錯誤顯示 retry。
 * - 選中項目透過 onChange 通知父層（父層通常將 policyId 寫入 URL search params）。
 */

import { useTranslation } from 'react-i18next'

import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { usePolicies } from '@/hooks/usePolicies'
import { formatPercent } from '@/utils/format'
import type { PolicyOption } from '@/viewmodels/policy'

export interface PolicyPickerProps {
  value: string | undefined
  onChange: (policyId: string) => void
  label?: string
}

export function PolicyPicker({ value, onChange, label }: PolicyPickerProps) {
  const { t } = useTranslation()
  const query = usePolicies()

  if (query.isPending) {
    return <LoadingSkeleton />
  }

  if (query.isError) {
    return (
      <div role="alert" className="text-sm text-danger">
        {query.error.message}
        <button
          type="button"
          className="ml-2 underline"
          onClick={() => query.refetch()}
        >
          {t('app.retry')}
        </button>
      </div>
    )
  }

  const policies: PolicyOption[] = query.data ?? []
  const resolvedValue = value ?? policies.find((p) => p.active)?.policyId ?? policies[0]?.policyId ?? ''

  return (
    <label className="flex flex-col gap-1 text-sm text-text-primary">
      <span className="font-medium">{label ?? t('settings.defaultPolicy.label')}</span>
      <select
        className="rounded border border-border bg-bg-surface px-2 py-1 text-sm text-text-primary"
        value={resolvedValue}
        onChange={(e) => onChange(e.target.value)}
      >
        {policies.map((p) => (
          <option key={p.policyId} value={p.policyId}>
            {p.displayName} · Sharpe {p.metrics.sharpeRatio.toFixed(2)} · MDD{' '}
            {formatPercent(p.metrics.maxDrawdown, { fractionDigits: 1 })}
          </option>
        ))}
      </select>
    </label>
  )
}
