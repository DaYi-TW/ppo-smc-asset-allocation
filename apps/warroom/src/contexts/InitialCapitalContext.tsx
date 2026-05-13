/**
 * InitialCapitalContext — 全域「初始投資金額」係數，純前端視覺乘數。
 *
 * 設計：
 *   - 不動 backend / artefact — PPO policy / reward / weight 都按 ratio 計算，
 *     乘任何數字都不會影響數學語意。
 *   - 顯示時把所有 NAV-like 數字（KPI / NAV chart / scrubber / observation table）
 *     乘 `initialCapital`，預設 1（保持當前語意：NAV 起始 1.0 ≈ +X% 報酬）。
 *   - 持久化到 localStorage（key = STORAGE_KEY），重整後保留。
 *   - Header 提供 input 讓使用者改（OverviewPage 內 InitialCapitalInput）。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

const STORAGE_KEY = 'ppo-smc-warroom.initialCapital'
const DEFAULT_INITIAL_CAPITAL = 1

interface InitialCapitalContextValue {
  initialCapital: number
  setInitialCapital: (next: number) => void
}

const InitialCapitalContext = createContext<InitialCapitalContextValue | null>(null)

function readFromStorage(): number {
  if (typeof window === 'undefined') return DEFAULT_INITIAL_CAPITAL
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw == null) return DEFAULT_INITIAL_CAPITAL
    const parsed = Number.parseFloat(raw)
    if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_INITIAL_CAPITAL
    return parsed
  } catch {
    return DEFAULT_INITIAL_CAPITAL
  }
}

export interface InitialCapitalProviderProps {
  children: ReactNode
}

export function InitialCapitalProvider({ children }: InitialCapitalProviderProps) {
  const [initialCapital, setInitialCapitalState] = useState<number>(() =>
    readFromStorage(),
  )

  const setInitialCapital = useCallback((next: number) => {
    const safe = Number.isFinite(next) && next > 0 ? next : DEFAULT_INITIAL_CAPITAL
    setInitialCapitalState(safe)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(STORAGE_KEY, String(initialCapital))
    } catch {
      // localStorage 不可用時靜默忽略
    }
  }, [initialCapital])

  const value = useMemo<InitialCapitalContextValue>(
    () => ({ initialCapital, setInitialCapital }),
    [initialCapital, setInitialCapital],
  )

  return (
    <InitialCapitalContext.Provider value={value}>
      {children}
    </InitialCapitalContext.Provider>
  )
}

/** 子元件讀「乘數」— Provider 缺席時 fallback 到 1（不破壞既有用法）。 */
export function useInitialCapital(): number {
  const ctx = useContext(InitialCapitalContext)
  return ctx?.initialCapital ?? DEFAULT_INITIAL_CAPITAL
}

/** 拿到 setter — 只有 InitialCapitalInput 用得到。 */
export function useSetInitialCapital(): (next: number) => void {
  const ctx = useContext(InitialCapitalContext)
  if (!ctx) {
    throw new Error('useSetInitialCapital must be used inside InitialCapitalProvider')
  }
  return ctx.setInitialCapital
}
