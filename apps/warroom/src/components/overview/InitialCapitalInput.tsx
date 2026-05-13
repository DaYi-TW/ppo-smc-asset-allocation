/**
 * InitialCapitalInput — header 輸入框，調整「初始投資金額」視覺乘數。
 *
 * - 純前端：NAV 系列數字（KPI / NAV chart / scrubber / observation table）顯示前
 *   乘 initialCapital。policy / reward / weight 計算不變。
 * - 持久化到 localStorage（透過 InitialCapitalContext）。
 * - 預設 $1 → 把 NAV 當作「報酬倍率」看；改成 100000 就變「美金本金 → 現值」。
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  useInitialCapital,
  useSetInitialCapital,
} from '@/contexts/InitialCapitalContext'

const PRESETS = [1, 1_000, 10_000, 100_000] as const

export function InitialCapitalInput() {
  const { t } = useTranslation()
  const initialCapital = useInitialCapital()
  const setInitialCapital = useSetInitialCapital()
  const [draft, setDraft] = useState<string>(String(initialCapital))

  // Context 值若被別處改動（preset 按鈕），同步 input 顯示
  useEffect(() => {
    setDraft(String(initialCapital))
  }, [initialCapital])

  const commit = (raw: string) => {
    const parsed = Number.parseFloat(raw.replace(/,/g, ''))
    if (Number.isFinite(parsed) && parsed > 0) {
      setInitialCapital(parsed)
    } else {
      setDraft(String(initialCapital))
    }
  }

  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
      <span className="whitespace-nowrap">
        {t('overview.initialCapital.label', '初始投資 $')}
      </span>
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            commit((e.target as HTMLInputElement).value)
            ;(e.target as HTMLInputElement).blur()
          }
        }}
        className="w-24 rounded-md border border-border bg-bg-elevated px-2 py-1 text-right font-mono text-text-primary outline-none focus:border-info"
        aria-label={t('overview.initialCapital.label', '初始投資 $')}
      />
      <span className="ml-1 hidden gap-1 md:inline-flex">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setInitialCapital(p)}
            className={`rounded border px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
              initialCapital === p
                ? 'border-info bg-info/15 text-info'
                : 'border-border bg-bg-elevated text-text-muted hover:border-info/40 hover:text-text-primary'
            }`}
            aria-pressed={initialCapital === p}
          >
            {p >= 1000 ? `${(p / 1000).toFixed(0)}k` : `$${p}`}
          </button>
        ))}
      </span>
    </label>
  )
}
