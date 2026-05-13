/**
 * EntryDateContext — 使用者設定的「進場日期」，全域共享。
 *
 * 與 timeline scrubber 的差異：
 *   - TimeRangeContext = 圖表視覺 zoom（[startIdx, endIdx]，可在進場日範圍內任意縮放）
 *   - EntryDateContext = 真實「進場日」，決定整段 dashboard 的資料起點
 *
 * 邏輯：
 *   - 預設 null → fallback 到整段第一個 frame 的日期
 *   - 使用者改進場日 → OverviewPage 把整段 frames 過濾成 timestamp >= entryDate，
 *     並 rescale NAV：進場日 NAV 重設為 1.0 × initialCapital，後續按 daily return
 *     從本金面值累積（語意 = 「假設你那天才進場」的回測視圖）
 *   - 持久化到 localStorage（ISO yyyy-mm-dd）
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

const STORAGE_KEY = 'ppo-smc-warroom.entryDate'

interface EntryDateContextValue {
  /** null = 用整段第一個 frame；string = ISO yyyy-mm-dd */
  entryDate: string | null
  setEntryDate: (next: string | null) => void
}

const EntryDateContext = createContext<EntryDateContextValue | null>(null)

function readFromStorage(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw == null || raw === '') return null
    // 簡單 sanity check：ISO yyyy-mm-dd
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null
    return raw
  } catch {
    return null
  }
}

export interface EntryDateProviderProps {
  children: ReactNode
}

export function EntryDateProvider({ children }: EntryDateProviderProps) {
  const [entryDate, setEntryDateState] = useState<string | null>(() => readFromStorage())

  const setEntryDate = useCallback((next: string | null) => {
    if (next === null) {
      setEntryDateState(null)
      return
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(next)) return
    setEntryDateState(next)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      if (entryDate == null) {
        window.localStorage.removeItem(STORAGE_KEY)
      } else {
        window.localStorage.setItem(STORAGE_KEY, entryDate)
      }
    } catch {
      // localStorage 不可用時靜默忽略
    }
  }, [entryDate])

  const value = useMemo<EntryDateContextValue>(
    () => ({ entryDate, setEntryDate }),
    [entryDate, setEntryDate],
  )

  return <EntryDateContext.Provider value={value}>{children}</EntryDateContext.Provider>
}

export function useEntryDate(): string | null {
  const ctx = useContext(EntryDateContext)
  return ctx?.entryDate ?? null
}

export function useSetEntryDate(): (next: string | null) => void {
  const ctx = useContext(EntryDateContext)
  if (!ctx) {
    throw new Error('useSetEntryDate must be used inside EntryDateProvider')
  }
  return ctx.setEntryDate
}
