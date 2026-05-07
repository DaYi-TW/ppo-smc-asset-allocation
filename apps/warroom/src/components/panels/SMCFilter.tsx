/**
 * SMCFilter — BOS/CHoCh/FVG/OB 顯隱 toggle。
 *
 * 對應 spec FR-005、FR-007。Toggle 狀態交由父層管理（URL 同步）。
 */

import { useTranslation } from 'react-i18next'

import type { SMCMarkerKind } from '@/viewmodels/smc'

const FILTER_GROUPS: ReadonlyArray<{ label: string; kinds: SMCMarkerKind[] }> = [
  { label: 'bos', kinds: ['BOS_BULL', 'BOS_BEAR'] },
  { label: 'choch', kinds: ['CHOCH_BULL', 'CHOCH_BEAR'] },
  { label: 'fvg', kinds: ['FVG'] },
  { label: 'ob', kinds: ['OB'] },
]

export interface SMCFilterProps {
  value: ReadonlySet<SMCMarkerKind>
  onChange: (next: Set<SMCMarkerKind>) => void
}

export function SMCFilter({ value, onChange }: SMCFilterProps) {
  const { t } = useTranslation()

  function toggleGroup(kinds: SMCMarkerKind[], checked: boolean) {
    const next = new Set(value)
    for (const k of kinds) {
      if (checked) next.add(k)
      else next.delete(k)
    }
    onChange(next)
  }

  return (
    <fieldset
      className="flex flex-wrap items-center gap-md rounded border border-border bg-bg-surface p-sm"
      aria-label={t('trajectory.smcFilter.label')}
    >
      <legend className="px-1 text-xs uppercase tracking-wide text-text-secondary">
        {t('trajectory.smcFilter.label')}
      </legend>
      {FILTER_GROUPS.map(({ label, kinds }) => {
        const allOn = kinds.every((k) => value.has(k))
        return (
          <label key={label} className="flex items-center gap-1 text-sm text-text-primary">
            <input
              type="checkbox"
              checked={allOn}
              onChange={(e) => toggleGroup(kinds, e.target.checked)}
            />
            <span>{t(`trajectory.kline.legend.${label}`)}</span>
          </label>
        )
      })}
    </fieldset>
  )
}

