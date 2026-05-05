/**
 * DecisionPage — US3 決策面板。
 *
 * 兩種模式（由 ?mode= 切換）：
 *  - mode=history（預設）：?episode=&step= — 顯示既有 trajectory 之歷史決策。
 *  - mode=live：訂閱 episodeId 之 SSE stream，顯示最新 progress。
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

import { RewardBreakdown } from '@/components/charts/RewardBreakdown'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ActionVector } from '@/components/panels/ActionVector'
import { DecisionNarration } from '@/components/panels/DecisionNarration'
import { EpisodePicker } from '@/components/panels/EpisodePicker'
import { ObservationTable } from '@/components/panels/ObservationTable'
import { useEpisodeDetail } from '@/hooks/useEpisodeDetail'
import { useEpisodeStream } from '@/hooks/useEpisodeStream'

type Mode = 'history' | 'live'

export function DecisionPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const episodeId = searchParams.get('episode') ?? undefined
  const mode = (searchParams.get('mode') as Mode | null) ?? 'history'
  const stepParam = Number.parseInt(searchParams.get('step') ?? '', 10)

  const detail = useEpisodeDetail(episodeId)
  const frames = detail.data?.trajectoryInline ?? []
  const stepIndex = Number.isFinite(stepParam)
    ? Math.max(0, Math.min(stepParam, frames.length - 1))
    : Math.max(0, frames.length - 1)
  const frame = frames[stepIndex]

  const stream = useEpisodeStream(episodeId, mode === 'live')

  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  const statusLabel = useMemo(() => {
    switch (stream.status) {
      case 'connecting':
        return t('decision.live.connecting')
      case 'open':
        return t('decision.live.open')
      case 'closed':
      case 'idle':
        return t('decision.live.closed')
      case 'error':
        return t('errors.sse.connectionFailed')
    }
  }, [stream.status, t])

  return (
    <section aria-labelledby="decision-heading" className="flex flex-col gap-lg">
      <header className="flex flex-col gap-md sm:flex-row sm:items-end sm:justify-between">
        <h2 id="decision-heading" className="text-2xl font-semibold text-text-primary">
          {t('decision.title')}
        </h2>
        <div className="flex flex-wrap items-end gap-md">
          <EpisodePicker
            value={episodeId}
            onChange={(id) => updateParam('episode', id)}
          />
          <fieldset className="flex items-end gap-2 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="decision-mode"
                checked={mode === 'history'}
                onChange={() => updateParam('mode', null)}
              />
              <span>history</span>
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="decision-mode"
                checked={mode === 'live'}
                onChange={() => updateParam('mode', 'live')}
              />
              <span>live</span>
            </label>
          </fieldset>
        </div>
      </header>

      {mode === 'live' && (
        <div
          role="status"
          className="rounded border border-border bg-bg-surface px-md py-sm text-sm text-text-primary"
        >
          <span className="font-medium">SSE: </span>
          {statusLabel}
          {stream.lastEvent && (
            <span className="ml-md text-text-secondary">
              last event: {JSON.stringify(stream.lastEvent)}
            </span>
          )}
          {(stream.status === 'error' || stream.status === 'closed') && (
            <button
              type="button"
              className="ml-md underline"
              onClick={stream.reconnect}
            >
              {t('decision.live.reconnect')}
            </button>
          )}
        </div>
      )}

      {!episodeId ? (
        <EmptyState title={t('trajectory.episodePicker.label')} />
      ) : detail.isPending ? (
        <LoadingSkeleton />
      ) : detail.isError ? (
        <div role="alert" className="text-sm text-danger">
          {detail.error.message}
        </div>
      ) : !frame ? (
        <EmptyState title={t('app.empty')} />
      ) : (
        <>
          <input
            type="range"
            min={0}
            max={frames.length - 1}
            value={stepIndex}
            onChange={(e) => updateParam('step', e.target.value)}
            aria-label="step"
            className="w-full"
          />
          <DecisionNarration frame={frame} />
          <div className="grid gap-lg lg:grid-cols-2">
            <article
              className="rounded-md border border-border bg-bg-surface p-md"
              aria-labelledby="obs-heading"
            >
              <h3 id="obs-heading" className="mb-sm text-lg font-medium text-text-primary">
                {t('decision.observation.title')}
              </h3>
              <ObservationTable frame={frame} />
            </article>
            <article
              className="rounded-md border border-border bg-bg-surface p-md"
              aria-labelledby="action-heading"
            >
              <h3 id="action-heading" className="mb-sm text-lg font-medium text-text-primary">
                {t('decision.action.title')}
              </h3>
              <ActionVector action={frame.action} />
            </article>
          </div>
          <article
            className="rounded-md border border-border bg-bg-surface p-md"
            aria-labelledby="reward-heading"
          >
            <h3 id="reward-heading" className="mb-sm text-lg font-medium text-text-primary">
              {t('decision.reward.title')}
            </h3>
            <RewardBreakdown series={detail.data.rewardBreakdown} step={stepIndex} />
          </article>
        </>
      )}
    </section>
  )
}
