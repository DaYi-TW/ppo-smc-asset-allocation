/**
 * EpisodePicker — 從 episode list 切換至指定 episode。
 *
 * Loading/error 處理同 PolicyPicker。父層通常將 value 同步進 URL。
 */

import { useTranslation } from 'react-i18next'

import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { useEpisodeList, type EpisodeListFilters } from '@/hooks/useEpisodeList'
import { formatDate, formatPercent } from '@/utils/format'

export interface EpisodePickerProps {
  value: string | undefined
  onChange: (episodeId: string) => void
  filters?: EpisodeListFilters
  label?: string
}

export function EpisodePicker({ value, onChange, filters, label }: EpisodePickerProps) {
  const { t } = useTranslation()
  const query = useEpisodeList(filters ?? {})

  if (query.isPending) return <LoadingSkeleton />

  if (query.isError) {
    return (
      <div role="alert" className="text-sm text-danger">
        {query.error.message}
        <button type="button" className="ml-2 underline" onClick={() => query.refetch()}>
          {t('app.retry')}
        </button>
      </div>
    )
  }

  const episodes = query.data ?? []
  const resolvedValue = value ?? episodes[0]?.episodeId ?? ''

  return (
    <label className="flex flex-col gap-1 text-sm text-text-primary">
      <span className="font-medium">{label ?? t('trajectory.episodePicker.label')}</span>
      <select
        className="rounded border border-border bg-bg-surface px-2 py-1 text-sm text-text-primary"
        value={resolvedValue}
        onChange={(e) => onChange(e.target.value)}
      >
        {episodes.map((ep) => (
          <option key={ep.episodeId} value={ep.episodeId}>
            {formatDate(ep.startDate)}–{formatDate(ep.endDate)} · {ep.policyId} ·{' '}
            {formatPercent(ep.totalReturn, { fractionDigits: 1 })}
          </option>
        ))}
      </select>
    </label>
  )
}
