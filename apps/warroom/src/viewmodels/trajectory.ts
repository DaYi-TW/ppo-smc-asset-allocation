/**
 * Trajectory ViewModel — 對應 data-model.md §3。
 *
 * Trajectory 為 episode 的時間序列資料；單一 frame 描述一個交易日結算狀態。
 */

import type { SMCSignals } from './smc'
import type { RewardSnapshot } from './reward'

export interface OHLCV {
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ActionVector {
  raw: number[]
  normalized: number[]
  logProb: number
  entropy: number
}

/** 權重分配 — 三層聚合 (riskOn/riskOff/cash) + per-asset 細項。
 *  Invariant: riskOn + riskOff + cash ≈ 1 (1e-6) ；perAsset 加總 ≈ riskOn + riskOff。 */
export interface WeightAllocation {
  riskOn: number
  riskOff: number
  cash: number
  perAsset: Record<string, number>
}

/** 單一 frame — 對應 trajectory parquet 的一列。 */
export interface TrajectoryFrame {
  timestamp: string
  step: number
  weights: WeightAllocation
  nav: number
  drawdownPct: number
  reward: RewardSnapshot
  smcSignals: SMCSignals
  ohlcv: OHLCV
  action: ActionVector
}
