/**
 * SMCToggleBar — K 線旁的 SMC 顯示開關。
 *
 * 4 個獨立結構 toggle：BOS / CHoCh / FVG / OB
 * 額外：Zigzag (swing 折線) + Active-only / 全歷史 切換。
 *
 * 每個 toggle 配一個 inline SVG 圖示，呼應 primitive 的實際畫法：
 *   BOS    — 實線水平箭頭（與 primitive 的 [4,3] 虛線同色系）
 *   CHoCh  — 點線水平箭頭（[1,3] 點線）
 *   FVG    — 半透明填色矩形（綠色系，bullish 範例）
 *   OB     — 半透明填色矩形（藍色系，bullish 範例）
 *   Zigzag — 折線串連 high/low
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
  Icon: () => JSX.Element
}

/** 24x12 圖示 — 用 currentColor 讓 active/inactive 樣式承襲按鈕字色。 */
function BosIcon() {
  // 綠色＝BOS bullish（與 primitive 的 theme.success 同色）
  const c = 'rgb(34, 197, 94)'
  return (
    <svg width="20" height="12" viewBox="0 0 24 12" aria-hidden>
      <line
        x1="2"
        y1="6"
        x2="20"
        y2="6"
        stroke={c}
        strokeWidth="1.5"
        strokeDasharray="4 3"
      />
      <polyline
        points="17,3 22,6 17,9"
        fill="none"
        stroke={c}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ChochIcon() {
  // 紫色＝CHoCh 專用色系（與 BOS 的綠/紅 success/danger 區隔，避免重疊難辨）
  const c = 'rgb(168, 85, 247)'
  return (
    <svg width="20" height="12" viewBox="0 0 24 12" aria-hidden>
      <line
        x1="2"
        y1="6"
        x2="20"
        y2="6"
        stroke={c}
        strokeWidth="1.5"
        strokeDasharray="1 3"
      />
      <polyline
        points="17,3 22,6 17,9"
        fill="none"
        stroke={c}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function FvgIcon() {
  return (
    <svg width="20" height="12" viewBox="0 0 24 12" aria-hidden>
      <rect
        x="2"
        y="2"
        width="20"
        height="8"
        fill="rgba(34,197,94,0.35)"
        stroke="rgba(34,197,94,0.85)"
        strokeWidth="1"
      />
    </svg>
  )
}

function ObIcon() {
  return (
    <svg width="20" height="12" viewBox="0 0 24 12" aria-hidden>
      <rect
        x="2"
        y="2"
        width="20"
        height="8"
        fill="rgba(59,130,246,0.35)"
        stroke="rgba(59,130,246,0.9)"
        strokeWidth="1"
      />
    </svg>
  )
}

function ZigzagIcon() {
  return (
    <svg width="22" height="12" viewBox="0 0 24 12" aria-hidden>
      <polyline
        points="2,9 7,3 12,8 17,4 22,9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
        strokeDasharray="2 2"
      />
      <circle cx="7" cy="3" r="1.4" fill="currentColor" />
      <circle cx="17" cy="4" r="1.4" fill="currentColor" />
    </svg>
  )
}

const STRUCTURE_TOGGLES: ToggleSpec[] = [
  { key: 'bos', label: 'BOS', hint: 'Break of Structure 破線', Icon: BosIcon },
  { key: 'choch', label: 'CHoCh', hint: 'Change of Character 反轉', Icon: ChochIcon },
  { key: 'fvg', label: 'FVG', hint: 'Fair Value Gap 矩形', Icon: FvgIcon },
  { key: 'ob', label: 'OB', hint: 'Order Block 矩形', Icon: ObIcon },
  { key: 'zigzag', label: 'Zigzag', hint: 'Swing high/low 折線', Icon: ZigzagIcon },
]

export function SMCToggleBar({ value, onChange }: SMCToggleBarProps) {
  const toggle = (k: keyof SMCVisibleConfig) => {
    onChange({ ...value, [k]: !value[k] })
  }
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      {STRUCTURE_TOGGLES.map((spec) => {
        const active = value[spec.key]
        const { Icon } = spec
        return (
          <button
            key={spec.key}
            type="button"
            onClick={() => toggle(spec.key)}
            title={spec.hint}
            aria-pressed={active}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10.5px] font-medium tracking-wide transition-colors ${
              active
                ? 'border-info bg-info/15 text-info'
                : 'border-border bg-bg-elevated text-text-secondary hover:border-info/40 hover:text-text-primary'
            }`}
          >
            <Icon />
            <span>{spec.label}</span>
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
