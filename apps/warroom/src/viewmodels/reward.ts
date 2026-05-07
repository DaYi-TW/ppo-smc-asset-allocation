/**
 * Reward 分解 — 對應 data-model.md §5。
 *
 * Invariant: total ≈ returnComponent - drawdownPenalty - costPenalty (1e-9 容差)。
 * drawdownPenalty / costPenalty 以正值儲存（顯示時 UI 加負號）。
 */

export interface RewardSnapshot {
  total: number
  returnComponent: number
  drawdownPenalty: number
  costPenalty: number
}

export interface RewardCumulativePoint {
  step: number
  cumulativeTotal: number
  cumulativeReturn: number
  cumulativeDrawdownPenalty: number
  cumulativeCostPenalty: number
}

export interface RewardSeries {
  cumulative: RewardCumulativePoint[]
  /** 與 trajectory 同長度，index 對齊 */
  byStep: RewardSnapshot[]
}
