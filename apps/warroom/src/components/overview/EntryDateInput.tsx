/**
 * EntryDateInput — header 日期選擇器，調整「進場日期」。
 *
 * - 範圍限制：[minDate, maxDate] = 整段第一個 frame ~ 末端
 * - 改了會：(1) 過濾 frames 為 timestamp >= entryDate
 *           (2) NAV rescale 把進場日重設為 1.0 × initialCapital
 *           (3) Timeline scrubber 自然變短
 * - Reset 按鈕回 null（= 整段預設）
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useEntryDate, useSetEntryDate } from '@/contexts/EntryDateContext'

export interface EntryDateInputProps {
  /** 整段資料的第一個 frame timestamp（yyyy-mm-dd） */
  minDate: string
  /** 整段資料的末端 frame timestamp（yyyy-mm-dd） */
  maxDate: string
}

export function EntryDateInput({ minDate, maxDate }: EntryDateInputProps) {
  const { t } = useTranslation()
  const entryDate = useEntryDate()
  const setEntryDate = useSetEntryDate()
  // input value 用 entryDate 或 minDate 當預設顯示
  const effective = entryDate ?? minDate
  const [draft, setDraft] = useState(effective)

  useEffect(() => {
    setDraft(effective)
  }, [effective])

  const commit = (val: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(val)) {
      setDraft(effective)
      return
    }
    // clamp 到 [minDate, maxDate]
    const clamped = val < minDate ? minDate : val > maxDate ? maxDate : val
    setEntryDate(clamped === minDate ? null : clamped)
    setDraft(clamped)
  }

  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
      <span className="whitespace-nowrap">
        {t('overview.entryDate.label', '進場日期')}
      </span>
      <input
        type="date"
        min={minDate}
        max={maxDate}
        value={draft}
        onChange={(e) => {
          // native date picker：選日期就 commit；手打字（部分輸入）會被 regex 擋掉
          const v = e.target.value
          setDraft(v)
          if (/^\d{4}-\d{2}-\d{2}$/.test(v)) commit(v)
        }}
        onBlur={(e) => commit(e.target.value)}
        className="rounded-md border border-border bg-bg-elevated px-2 py-1 font-mono text-text-primary outline-none focus:border-info"
        aria-label={t('overview.entryDate.label', '進場日期')}
      />
      {entryDate != null && (
        <button
          type="button"
          onClick={() => setEntryDate(null)}
          className="rounded border border-border bg-bg-elevated px-1.5 py-0.5 text-[10px] text-text-muted transition-colors hover:text-text-primary"
          title={t('overview.entryDate.reset', '回到整段起點')}
        >
          {t('overview.entryDate.resetLabel', '回到起點')}
        </button>
      )}
    </label>
  )
}
