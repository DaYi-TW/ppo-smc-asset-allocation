/**
 * TimeRangeContext — 全域 timeline scrubber 共享 [startIdx, endIdx] 給所有圖表。
 *
 * 設計選擇：用 frame index（而非 timestamp string）共享，避免下游圖表都要做
 * timestamp → index 反查。OverviewPage 是唯一的 provider；子元件透過
 * useTimeRange() 讀取，必要時透過 setRange() 寫入（例如 scrubber 拖動）。
 *
 * 預設範圍 = 最近 1 個月（~21 個交易日，用 DEFAULT_WINDOW_FRAMES 控制）。
 * 切換 episode 時會以同樣窗格重設。Reset 按鈕（在 TimelineScrubber）才會展回全段。
 */

/** 預設視窗：21 個交易日 ≈ 1 個月。 */
// eslint-disable-next-line react-refresh/only-export-components
export const DEFAULT_WINDOW_FRAMES = 21

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export interface TimeRange {
  /** Inclusive start index. */
  start: number
  /** Exclusive end index — slice-style，方便 frames.slice(start, end)。 */
  end: number
}

interface TimeRangeContextValue {
  range: TimeRange
  setRange: (next: TimeRange) => void
  totalFrames: number
}

const TimeRangeContext = createContext<TimeRangeContextValue | null>(null)

export interface TimeRangeProviderProps {
  totalFrames: number
  children: ReactNode
}

function defaultRange(totalFrames: number): TimeRange {
  if (totalFrames <= 0) return { start: 0, end: 0 }
  const end = totalFrames
  const start = Math.max(0, end - DEFAULT_WINDOW_FRAMES)
  return { start, end }
}

export function TimeRangeProvider({ totalFrames, children }: TimeRangeProviderProps) {
  const [range, setRangeState] = useState<TimeRange>(() => defaultRange(totalFrames))

  // frames 長度變化（例如切換 episode）時重設為預設視窗
  useEffect(() => {
    setRangeState(defaultRange(totalFrames))
  }, [totalFrames])

  const value = useMemo<TimeRangeContextValue>(() => {
    const setRange = (next: TimeRange) => {
      const clampedStart = Math.max(0, Math.min(next.start, totalFrames))
      const clampedEnd = Math.max(clampedStart, Math.min(next.end, totalFrames))
      setRangeState({ start: clampedStart, end: clampedEnd })
    }
    return { range, setRange, totalFrames }
  }, [range, totalFrames])

  return <TimeRangeContext.Provider value={value}>{children}</TimeRangeContext.Provider>
}

/** 使用 hook；OverviewPage 之外呼叫會 fallback 為全範圍（不報錯，方便獨立測試 chart）。 */
// eslint-disable-next-line react-refresh/only-export-components
export function useTimeRange(fallbackTotal = 0): TimeRangeContextValue {
  const ctx = useContext(TimeRangeContext)
  if (ctx) return ctx
  return {
    range: { start: 0, end: fallbackTotal },
    setRange: () => undefined,
    totalFrames: fallbackTotal,
  }
}
