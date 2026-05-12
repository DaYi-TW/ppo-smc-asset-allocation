/**
 * Feature 010 FR-023 / FR-024 / FR-025 — 「手動更新到最新」按鈕。
 *
 * 行為：
 *   - status.is_running=true 或 mutation.isPending → disabled + spinner
 *   - 點擊 → trigger refresh mutation
 *   - 結果分流（FR-016 + FR-024 + FR-025）：
 *       * accepted → 不彈 toast（UI 由 polling 自動跟上）
 *       * conflict → toast「正在更新中（pid=N）」（友善，不視為錯誤）
 *       * error    → toast 錯誤訊息（FR-025；包 last_error 字串）
 *
 * Toast 用 sessionStorage / DOM event 暫不實作，先以 prop callback 形式暴露給上層
 * （OverviewPage 統一掛 toast provider）— 元件本身保持 dumb，方便測試。
 */

import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'

import type { RefreshResult } from '@/api/episodes'
import type { UseMutationResult } from '@tanstack/react-query'

export interface LiveRefreshButtonProps {
  refresh: UseMutationResult<RefreshResult, Error, void>
  /** 來自 status.is_running — pipeline 已在跑時也要 disable */
  isPipelineRunning?: boolean
  /** 結果通知（success / conflict / error）—上層綁 toast */
  onResult?: (
    result:
      | { kind: 'accepted'; payload: RefreshResult & { status: 'accepted' } }
      | { kind: 'conflict'; payload: RefreshResult & { status: 'conflict' } }
      | { kind: 'error'; error: Error },
  ) => void
}

export function LiveRefreshButton({
  refresh,
  isPipelineRunning = false,
  onResult,
}: LiveRefreshButtonProps) {
  const { t } = useTranslation()
  const isBusy = refresh.isPending || isPipelineRunning

  const handleClick = useCallback(() => {
    refresh.mutate(undefined, {
      onSuccess: (result) => {
        if (!onResult) return
        if (result.status === 'accepted') {
          onResult({ kind: 'accepted', payload: result })
        } else {
          onResult({ kind: 'conflict', payload: result })
        }
      },
      onError: (error) => {
        if (onResult) onResult({ kind: 'error', error })
      },
    })
  }, [refresh, onResult])

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isBusy}
      data-testid="live-refresh-button"
      aria-busy={isBusy}
      className="inline-flex items-center gap-xs rounded-md border border-accent bg-accent/10 px-md py-sm text-sm font-medium text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {isBusy && (
        <span
          data-testid="live-refresh-spinner"
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent"
          aria-hidden="true"
        />
      )}
      {isBusy
        ? t('liveTracking.button.running', '更新中…')
        : t('liveTracking.button.refresh', '手動更新到最新')}
    </button>
  )
}
