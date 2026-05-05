/**
 * OverviewPage — US1 戰情總覽。
 *
 * 組合：
 *  - PolicyPicker（URL state sync `?policy=`）
 *  - EpisodeMeta（總報酬 / Sharpe / MDD / 步數）
 *  - WeightStackedArea（7 維權重堆疊）
 *  - NavDrawdownChart（NAV + drawdown）
 *
 * 資料源：useEpisodeList(policy) → 取最新 completed → useEpisodeDetail。
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

import { NavDrawdownChart } from '@/components/charts/NavDrawdownChart'
import { WeightStackedArea } from '@/components/charts/WeightStackedArea'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { EpisodeMeta } from '@/components/panels/EpisodeMeta'
import { PolicyPicker } from '@/components/panels/PolicyPicker'
import { useEpisodeDetail } from '@/hooks/useEpisodeDetail'
import { useEpisodeList } from '@/hooks/useEpisodeList'

export function OverviewPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const policyId = searchParams.get('policy') ?? undefined

  const handlePolicyChange = (next: string) => {
    const params = new URLSearchParams(searchParams)
    params.set('policy', next)
    setSearchParams(params, { replace: true })
  }

  const listFilters = useMemo(
    () => ({ ...(policyId ? { policyId } : {}), status: 'completed' as const, pageSize: 1 }),
    [policyId],
  )
  const listQuery = useEpisodeList(listFilters)
  const latestEpisode = listQuery.data?.[0]
  const detailQuery = useEpisodeDetail(latestEpisode?.episodeId)

  const frames = detailQuery.data?.trajectoryInline ?? []
  const isLoading = listQuery.isPending || detailQuery.isPending

  return (
    <section aria-labelledby="overview-heading" className="flex flex-col gap-lg">
      <header className="flex flex-col gap-md sm:flex-row sm:items-end sm:justify-between">
        <h2 id="overview-heading" className="text-2xl font-semibold text-text-primary">
          {t('overview.title')}
        </h2>
        <PolicyPicker value={policyId} onChange={handlePolicyChange} />
      </header>

      {isLoading ? (
        <LoadingSkeleton />
      ) : !latestEpisode ? (
        <EmptyState title={t('app.empty')} />
      ) : (
        <>
          <EpisodeMeta episode={latestEpisode} />
          <article
            className="rounded-md border border-border bg-bg-surface p-md"
            aria-labelledby="weight-chart-heading"
          >
            <h3 id="weight-chart-heading" className="mb-sm text-lg font-medium text-text-primary">
              {t('overview.weightChart.title')}
            </h3>
            <WeightStackedArea frames={frames} />
          </article>
          <article
            className="rounded-md border border-border bg-bg-surface p-md"
            aria-labelledby="nav-chart-heading"
          >
            <h3 id="nav-chart-heading" className="mb-sm text-lg font-medium text-text-primary">
              {t('overview.navChart.title')}
            </h3>
            <NavDrawdownChart frames={frames} />
          </article>
        </>
      )}
    </section>
  )
}
