/**
 * Feature 010 T056 / FR-025 / SC-009 — 失敗訊息 banner。
 *
 * 行為：
 *   - lastError === null → 不渲染（return null）
 *   - lastError !== null → 渲染 persistent banner，含：
 *       * 失敗時間（lastUpdated ISO）
 *       * 錯誤訊息（last_error 字串，含 DATA_FETCH:/INFERENCE:/WRITE: 前綴）
 *       * 「再試一次」按鈕 → trigger refresh.mutate
 *
 * 純 presentational — pipeline 失敗分類與訊息來自 005 status endpoint
 * （見 src/live_tracking/pipeline.py 的 _fail prefix 與 T053 test）。
 *
 * banner 不會自動消失 — 由父層在 mutation 成功後 invalidate query → status.last_error
 * 變 null → 元件自動 unmount。
 */

import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'

import type { RefreshResult } from '@/api/episodes'
import type { UseMutationResult } from '@tanstack/react-query'

export interface FailureToastProps {
  /** ``status.last_error`` 字串；null 時元件不渲染 */
  lastError: string | null
  /** ``status.last_updated`` ISO 字串 */
  lastUpdated: string | null
  /** 來自 useLiveRefresh().refresh — 點「再試」直接 mutate */
  refresh: UseMutationResult<RefreshResult, Error, void>
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  // 取 YYYY-MM-DD HH:MM 局部顯示，不依賴 toLocaleString（測試環境 i18n 不穩）
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi} UTC`
}

export function FailureToast({
  lastError,
  lastUpdated,
  refresh,
}: FailureToastProps) {
  const { t } = useTranslation()

  const handleRetry = useCallback(() => {
    refresh.mutate(undefined)
  }, [refresh])

  if (lastError === null) return null

  const isBusy = refresh.isPending

  return (
    <div
      role="alert"
      data-testid="failure-toast"
      className="flex flex-wrap items-start gap-sm rounded-md border border-danger/40 bg-danger/10 px-md py-sm text-sm text-danger"
    >
      <div className="flex flex-1 flex-col gap-xs">
        <div className="text-xs text-danger/80">
          {t('liveTracking.failure.title', '更新失敗')}
          <span className="ml-2 font-mono text-[11px]">
            {formatTimestamp(lastUpdated)}
          </span>
        </div>
        <div className="break-words font-mono text-xs">{lastError}</div>
      </div>
      <button
        type="button"
        onClick={handleRetry}
        disabled={isBusy}
        data-testid="failure-toast-retry"
        className="shrink-0 rounded-md border border-danger px-sm py-xs text-xs font-medium hover:bg-danger/20 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {t('liveTracking.failure.retry', '再試一次')}
      </button>
    </div>
  )
}
