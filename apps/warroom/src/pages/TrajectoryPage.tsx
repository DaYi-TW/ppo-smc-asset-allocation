/**
 * TrajectoryPage — US2 軌跡分析 + SMC 標記。
 *
 * URL state：
 *  - ?episode= — 當前 episode id
 *  - ?smc=    — 逗號分隔顯示中的 SMC marker kinds（缺省 = 全部）
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

import { KLineWithSMC } from '@/components/charts/KLineWithSMC'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { EpisodePicker } from '@/components/panels/EpisodePicker'
import { SMCFilter } from '@/components/panels/SMCFilter'
import { useTrajectory } from '@/hooks/useTrajectory'
import type { SMCMarkerKind } from '@/viewmodels/smc'
import { ALL_SMC_KINDS } from '@/viewmodels/smc-constants'

const ALL_KIND_SET = new Set<SMCMarkerKind>(ALL_SMC_KINDS)

function parseSmcParam(raw: string | null): Set<SMCMarkerKind> {
  if (raw === null || raw === '') return new Set(ALL_KIND_SET)
  const parts = raw.split(',').filter((s): s is SMCMarkerKind =>
    (ALL_SMC_KINDS as ReadonlyArray<string>).includes(s),
  )
  return parts.length === 0 ? new Set(ALL_KIND_SET) : new Set(parts)
}

function formatSmcParam(set: ReadonlySet<SMCMarkerKind>): string | null {
  if (set.size === ALL_KIND_SET.size) return null
  return Array.from(set).join(',')
}

export function TrajectoryPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const episodeId = searchParams.get('episode') ?? undefined
  const smcKinds = useMemo(() => parseSmcParam(searchParams.get('smc')), [searchParams])

  const trajectory = useTrajectory(episodeId)

  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  return (
    <section aria-labelledby="trajectory-heading" className="flex flex-col gap-lg">
      <header className="flex flex-col gap-md sm:flex-row sm:items-end sm:justify-between">
        <h2 id="trajectory-heading" className="text-2xl font-semibold text-text-primary">
          {t('trajectory.title')}
        </h2>
        <EpisodePicker
          value={episodeId}
          onChange={(id) => updateParam('episode', id)}
        />
      </header>

      <SMCFilter
        value={smcKinds}
        onChange={(next) => updateParam('smc', formatSmcParam(next))}
      />

      {!episodeId ? (
        <EmptyState title={t('trajectory.episodePicker.label')} />
      ) : trajectory.isPending ? (
        <LoadingSkeleton />
      ) : trajectory.isError ? (
        <div role="alert" className="text-sm text-danger">
          {trajectory.error.message}
        </div>
      ) : (
        <article
          className="rounded-md border border-border bg-bg-surface p-md"
          aria-labelledby="kline-heading"
        >
          <h3 id="kline-heading" className="mb-sm text-lg font-medium text-text-primary">
            {t('trajectory.kline.title')}
          </h3>
          <KLineWithSMC frames={trajectory.data ?? []} visibleKinds={smcKinds} />
          <p className="mt-sm text-xs text-text-secondary">
            {t('trajectory.frameCount', { count: trajectory.data?.length ?? 0 })}
          </p>
        </article>
      )}
    </section>
  )
}
