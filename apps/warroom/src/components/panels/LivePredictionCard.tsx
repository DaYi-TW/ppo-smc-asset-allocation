/**
 * Live Prediction 卡 — Settings 頁底用。
 *
 * 顯示 006 Gateway 回的最新一筆 PredictionPayload；提供「立即重跑」按鈕。
 * 連上 SSE 後背景 push 也會自動更新。
 */

import { useTranslation } from 'react-i18next'

import { useLivePrediction } from '@/hooks/useLivePrediction'
import { formatPercent } from '@/utils/format'
import type { PredictionPayload, TriggeredBy } from '@/viewmodels/prediction'

function triggeredLabel(t: (k: string) => string, by: TriggeredBy): string {
  return by === 'manual' ? t('livePrediction.triggered.manual') : t('livePrediction.triggered.scheduled')
}

function WeightsList({ weights }: { weights: PredictionPayload['targetWeights'] }) {
  const entries = Object.entries(weights).sort(([, a], [, b]) => b - a)
  return (
    <ul className="grid grid-cols-2 gap-x-md gap-y-xs sm:grid-cols-3">
      {entries.map(([ticker, weight]) => (
        <li key={ticker} className="flex justify-between font-mono text-sm">
          <span className="text-text-secondary">{ticker}</span>
          <span className="text-text-primary">{formatPercent(weight, { fractionDigits: 1 })}</span>
        </li>
      ))}
    </ul>
  )
}

export function LivePredictionCard() {
  const { t } = useTranslation()
  const { latest, run } = useLivePrediction()

  const payload = latest.data
  const isNotReady = latest.isError && latest.error.httpStatus === 404
  const showError = latest.isError && !isNotReady
  const runError = run.isError ? run.error : undefined

  return (
    <section
      aria-labelledby="live-prediction-heading"
      className="rounded-md border border-default bg-bg-elevated p-md flex flex-col gap-sm max-w-xl"
    >
      <header className="flex items-center justify-between gap-sm">
        <h3 id="live-prediction-heading" className="text-lg font-semibold text-text-primary">
          {t('livePrediction.title')}
        </h3>
        <button
          type="button"
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="rounded-sm bg-accent px-md py-xs text-sm text-bg-primary disabled:opacity-50"
        >
          {run.isPending ? t('livePrediction.running') : t('livePrediction.runNow')}
        </button>
      </header>

      {latest.isLoading && <p className="text-sm text-text-secondary">{t('app.loading')}</p>}

      {isNotReady && !payload && (
        <p className="text-sm text-text-secondary">{t('livePrediction.notReady')}</p>
      )}

      {showError && (
        <p className="text-sm text-error" role="alert">
          {t('livePrediction.fetchFailed')}（{latest.error.code}）
        </p>
      )}

      {payload && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-md gap-y-xs text-sm">
          <dt className="text-text-secondary">{t('livePrediction.asOf')}</dt>
          <dd className="text-text-primary">{payload.asOfDate}</dd>

          <dt className="text-text-secondary">{t('livePrediction.target')}</dt>
          <dd className="text-text-primary">{payload.nextTradingDayTarget}</dd>

          <dt className="text-text-secondary">{t('livePrediction.triggered.label')}</dt>
          <dd className="text-text-primary">{triggeredLabel(t, payload.triggeredBy)}</dd>

          <dt className="text-text-secondary">{t('livePrediction.inferredAt')}</dt>
          <dd className="text-text-primary font-mono text-xs">{payload.inferredAtUtc}</dd>

          <dt className="self-start text-text-secondary">{t('livePrediction.weights')}</dt>
          <dd>
            <WeightsList weights={payload.targetWeights} />
          </dd>
        </dl>
      )}

      {runError && (
        <p className="text-sm text-error" role="alert">
          {t('livePrediction.runFailed')}（{runError.code}）
        </p>
      )}
    </section>
  )
}
