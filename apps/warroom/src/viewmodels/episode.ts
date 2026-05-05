/**
 * Episode 相關 ViewModel — 對應 data-model.md §2。
 *
 * Episode 表示單一 PPO policy 在某 trajectory 上的一次 deterministic 評估，
 * 對應 src/ppo_training/evaluate.py 之輸出。
 */

import type { TrajectoryFrame } from './trajectory'
import type { RewardSeries } from './reward'

export type EpisodeStatus = 'pending' | 'running' | 'completed' | 'failed'

/** 對應 GET /api/v1/episodes 陣列元素 */
export interface EpisodeSummaryViewModel {
  episodeId: string
  policyId: string
  policyVersion: string
  startDate: string
  endDate: string
  totalReturn: number
  maxDrawdown: number
  sharpeRatio: number
  totalSteps: number
  status: EpisodeStatus
  createdAt: string
}

export interface EpisodeConfig {
  initialNav: number
  symbols: string[]
  rebalanceFrequency: 'daily' | 'weekly'
  transactionCostBps: number
  slippageBps: number
  riskFreeRate: number
}

/** 對應 GET /api/v1/episodes/{id}。
 *  Invariant: trajectoryUri 與 trajectoryInline 互斥（XOR）。 */
export interface EpisodeDetailViewModel extends EpisodeSummaryViewModel {
  config: EpisodeConfig
  trajectoryUri?: string
  trajectoryInline?: TrajectoryFrame[]
  rewardBreakdown: RewardSeries
  errorMessage?: string
}
