/**
 * KeyboardShortcutsHelp — 按 `?` 開啟 modal 顯示快捷鍵列表。
 *
 * 範圍：僅顯示既存路由導覽（不新增 hot-path 快捷以免誤觸）。
 */

import { useEffect, useState } from 'react'

const SHORTCUTS: ReadonlyArray<{ keys: string; description: string }> = [
  { keys: '?', description: 'Open this help' },
  { keys: 'Esc', description: 'Close dialog / clear focus' },
  { keys: '←/→', description: 'Trajectory step (when focused)' },
]

export function KeyboardShortcutsHelp() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (e.key === '?' && !open) {
        e.preventDefault()
        setOpen(true)
      } else if (e.key === 'Escape' && open) {
        e.preventDefault()
        setOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 z-modal flex items-center justify-center bg-black/40"
      onClick={() => setOpen(false)}
    >
      <div
        className="rounded-md bg-bg-surface text-text-primary border border-default p-lg max-w-md w-full mx-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-md">Keyboard Shortcuts</h2>
        <ul className="flex flex-col gap-sm text-sm">
          {SHORTCUTS.map((s) => (
            <li key={s.keys} className="flex justify-between">
              <kbd className="px-xs py-1 rounded-sm bg-bg-elevated border border-default font-mono">
                {s.keys}
              </kbd>
              <span className="text-text-secondary">{s.description}</span>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="mt-md px-md py-sm rounded-sm bg-primary text-white hover:bg-primary-hover"
        >
          Close
        </button>
      </div>
    </div>
  )
}
