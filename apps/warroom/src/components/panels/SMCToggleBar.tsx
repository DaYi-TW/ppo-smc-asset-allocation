/**
 * SMCToggleBar — K 線旁的 SMC 顯示開關。
 *
 * 4 個獨立結構 toggle：BOS / CHoCh / FVG / OB
 * 額外：Zigzag (swing 折線) + Active-only / 全歷史 切換。
 */

import type { SMCVisibleConfig } from '@/components/charts/smcOverlayPrimitive'

export interface SMCToggleBarProps {
  value: SMCVisibleConfig
  onChange: (next: SMCVisibleConfig) => void
}

interface ToggleSpec {
  key: keyof Omit<SMCVisibleConfig, 'activeOnly'>
  label: string
  hint: string
}

const STRUCTURE_TOGGLES: ToggleSpec[] = [
  { key: 'bos', label: 'BOS', hint: 'Break of Structure 破線' },
  { key: 'choch', label: 'CHoCh', hint: 'Change of Character 反轉' },
  { key: 'fvg', label: 'FVG', hint: 'Fair Value Gap 矩形' },
  { key: 'ob', label: 'OB', hint: 'Order Block 矩形' },
  { key: 'zigzag', label: 'Zigzag', hint: 'Swing high/low 折線' },
]

export function SMCToggleBar({ value, onChange }: SMCToggleBarProps) {
  const toggle = (k: keyof SMCVisibleConfig) => {
    onChange({ ...value, [k]: !value[k] })
  }
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      {STRUCTURE_TOGGLES.map((spec) => {
        const active = value[spec.key]
        return (
          <button
            key={spec.key}
            type="button"
            onClick={() => toggle(spec.key)}
            title={spec.hint}
            aria-pressed={active}
            className={`rounded-md border px-2 py-0.5 text-[10.5px] font-medium tracking-wide transition-colors ${
              active
                ? 'border-info bg-info/15 text-info'
                : 'border-border bg-bg-elevated text-text-secondary hover:border-info/40 hover:text-text-primary'
            }`}
          >
            {spec.label}
          </button>
        )
      })}
      <div className="ml-2 h-4 w-px bg-border" aria-hidden />
      <button
        type="button"
        onClick={() => toggle('activeOnly')}
        title={
          value.activeOnly
            ? '只顯示 active：未填補 FVG、未失效 OB（點擊改顯示全歷史）'
            : '顯示全部歷史 FVG/OB（點擊改 active-only）'
        }
        aria-pressed={value.activeOnly}
        className={`rounded-md border px-2 py-0.5 text-[10.5px] font-medium tracking-wide transition-colors ${
          value.activeOnly
            ? 'border-warning bg-warning/15 text-warning'
            : 'border-border bg-bg-elevated text-text-secondary hover:border-warning/40 hover:text-text-primary'
        }`}
      >
        {value.activeOnly ? 'Active' : 'History'}
      </button>
    </div>
  )
}
