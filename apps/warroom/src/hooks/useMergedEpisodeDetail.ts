/**
 * useMergedEpisodeDetail — 把 OOS episode 與 Live episode 兩個 detail merge 成一個
 * EpisodeDetailViewModel，前端就能在同一張 NAV 線 / 權重圖 / SMC overlay 上看到完整
 * 「2026-01-01 → today」連續視圖。
 *
 * Merge 規則：
 *   - trajectoryInline：OOS frames + Live frames，依日期遞增排列。Live 段 NAV 要
 *     rescale — Live 的 frame 0 起始 nav = 1.0（initial capital），但 OOS 末端
 *     nav 通常不等於 1.0，直接 concat 會在 4/28 → 4/29 造成「掉回 1.0」斷崖。
 *     做法：取 Live frame 之 daily return = nav[t]/nav[t-1]，從 OOS finalNav 重新
 *     累積。step 也要 offset（Live 的 step 0 → OOS.length + 0）。
 *   - rewardBreakdown.byStep：直接 concat（per-step 是局部值，不需 rescale）。
 *   - rewardBreakdown.cumulative：以 merged byStep 重算（cumulative 跨段必須連續）。
 *   - smcOverlayByAsset：每個 asset 的 swings/zigzag/fvgs/obs/breaks 都是 list，
 *     OOS + Live concat 即可；如 asset 兩段都有 overlay，list 合併並沿 time 排序。
 *   - summary 欄位：
 *       startDate → OOS.startDate
 *       endDate   → Live.endDate
 *       totalReturn → (mergedFinalNav / OOS.initialNav) - 1
 *       maxDrawdown → 重算整段 frames 的 running peak / drawdown
 *       sharpeRatio → 重算整段 daily returns 的 Sharpe（簡化：rf = 0）
 *       totalSteps → OOS.totalSteps + Live.totalSteps
 *
 * 若 Live 不存在（首次部署或 reset），fallback 到純 OOS detail；
 * 若 OOS 不存在（理論上不會發生），fallback 到純 Live detail。
 */

import { useMemo } from 'react'

import { useEpisodeDetail } from './useEpisodeDetail'
import type { EpisodeDetailViewModel } from '@/viewmodels/episode'
import type {
  RewardCumulativePoint,
  RewardSeries,
  RewardSnapshot,
} from '@/viewmodels/reward'
import type { SMCOverlay } from '@/viewmodels/smc'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

interface MergeResult {
  data: EpisodeDetailViewModel | undefined
  isPending: boolean
  isError: boolean
}

export interface UseMergedEpisodeDetailParams {
  oosEpisodeId: string | undefined
  liveEpisodeId: string | undefined
}

export function useMergedEpisodeDetail({
  oosEpisodeId,
  liveEpisodeId,
}: UseMergedEpisodeDetailParams): MergeResult {
  const oosQuery = useEpisodeDetail(oosEpisodeId)
  const liveQuery = useEpisodeDetail(liveEpisodeId)

  const merged = useMemo<EpisodeDetailViewModel | undefined>(() => {
    const oos = oosQuery.data
    const live = liveQuery.data
    if (!oos && !live) return undefined
    if (!live) return oos
    if (!oos) return live
    return mergeOosAndLive(oos, live)
  }, [oosQuery.data, liveQuery.data])

  const oosWanted = Boolean(oosEpisodeId)
  const liveWanted = Boolean(liveEpisodeId)
  // pending 條件：想抓的 query 還在跑。只要任何一邊還在 pending，UI 顯示 loading。
  const isPending =
    (oosWanted && oosQuery.isPending) || (liveWanted && liveQuery.isPending)
  const isError =
    (oosWanted && oosQuery.isError) || (liveWanted && liveQuery.isError)

  return { data: merged, isPending, isError }
}

function mergeOosAndLive(
  oos: EpisodeDetailViewModel,
  live: EpisodeDetailViewModel,
): EpisodeDetailViewModel {
  const oosFrames = oos.trajectoryInline ?? []
  const liveFrames = live.trajectoryInline ?? []

  const oosFinalNav = oosFrames[oosFrames.length - 1]?.nav ?? oos.config.initialNav
  const liveBaseNav = liveFrames[0]?.nav ?? 1

  // Live frames rescale：用 daily return 從 OOS finalNav 重新累積。
  // 第一個 Live frame 與 OOS final 銜接（return = liveFrames[0].nav / liveBaseNav = 1.0），
  // 第二個之後用 nav[t]/nav[t-1] 一階差分累積。
  const rescaledLiveFrames: TrajectoryFrame[] = []
  let prevLiveNavOriginal = liveBaseNav
  let runningNav = oosFinalNav
  for (let i = 0; i < liveFrames.length; i += 1) {
    const f = liveFrames[i]
    if (!f) continue
    const ret = prevLiveNavOriginal > 0 ? f.nav / prevLiveNavOriginal : 1
    runningNav = i === 0 ? oosFinalNav * ret : runningNav * ret
    rescaledLiveFrames.push({
      ...f,
      step: oosFrames.length + i,
      nav: runningNav,
    })
    prevLiveNavOriginal = f.nav
  }

  const allFrames: TrajectoryFrame[] = [...oosFrames, ...rescaledLiveFrames]

  // 重算 drawdownPct（running peak 從整段重起）— Live 段的 drawdownPct 也要更新，
  // 因為 NAV 已被 rescale。
  const reframedFrames = recomputeDrawdown(allFrames)

  // Reward byStep 直接 concat；cumulative 從 byStep 重算（跨段必須連續）。
  const mergedByStep: RewardSnapshot[] = [
    ...oos.rewardBreakdown.byStep,
    ...live.rewardBreakdown.byStep,
  ]
  const mergedCumulative = recomputeCumulative(mergedByStep)

  const mergedReward: RewardSeries = {
    byStep: mergedByStep,
    cumulative: mergedCumulative,
  }

  // SMC overlay：兩段 list 合併並按 time 排序（zone/swing 都帶 ISO date）。
  const mergedOverlay = mergeOverlays(
    oos.smcOverlayByAsset ?? {},
    live.smcOverlayByAsset ?? {},
  )

  // Summary 重算
  const mergedFinalNav = reframedFrames[reframedFrames.length - 1]?.nav ?? oosFinalNav
  const mergedTotalReturn =
    oos.config.initialNav > 0 ? mergedFinalNav / oos.config.initialNav - 1 : 0
  const mergedMaxDrawdown = computeMaxDrawdownPct(reframedFrames)
  const mergedSharpe = computeAnnualizedSharpe(reframedFrames)

  return {
    ...oos,
    // 用 live 的 id 當主鍵讓 React Query / URL 維持指向 live；前端不會因此誤判
    episodeId: live.episodeId,
    startDate: oos.startDate,
    endDate: live.endDate,
    totalReturn: mergedTotalReturn,
    maxDrawdown: mergedMaxDrawdown,
    sharpeRatio: mergedSharpe,
    totalSteps: reframedFrames.length,
    trajectoryInline: reframedFrames,
    rewardBreakdown: mergedReward,
    smcOverlayByAsset: mergedOverlay,
  }
}

function recomputeDrawdown(
  frames: ReadonlyArray<TrajectoryFrame>,
): TrajectoryFrame[] {
  let peak = -Infinity
  return frames.map((f) => {
    if (f.nav > peak) peak = f.nav
    const drawdownPct = peak > 0 ? (f.nav - peak) / peak : 0
    return { ...f, drawdownPct }
  })
}

export function computeMaxDrawdownPct(
  frames: ReadonlyArray<TrajectoryFrame>,
): number {
  let peak = -Infinity
  let mdd = 0
  for (const f of frames) {
    if (f.nav > peak) peak = f.nav
    const dd = peak > 0 ? (f.nav - peak) / peak : 0
    if (dd < mdd) mdd = dd
  }
  return mdd
}

export function computeAnnualizedSharpe(
  frames: ReadonlyArray<TrajectoryFrame>,
): number {
  if (frames.length < 2) return 0
  const dailyReturns: number[] = []
  for (let i = 1; i < frames.length; i += 1) {
    const prev = frames[i - 1]
    const curr = frames[i]
    if (!prev || !curr || prev.nav <= 0) continue
    dailyReturns.push(curr.nav / prev.nav - 1)
  }
  if (dailyReturns.length === 0) return 0
  const mean = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length
  const variance =
    dailyReturns.reduce((a, b) => a + (b - mean) ** 2, 0) / dailyReturns.length
  const std = Math.sqrt(variance)
  if (std === 0) return 0
  // 252 交易日年化，rf=0（與 005 summary 計算一致簡化）
  return (mean / std) * Math.sqrt(252)
}

function recomputeCumulative(
  byStep: ReadonlyArray<RewardSnapshot>,
): RewardCumulativePoint[] {
  const out: RewardCumulativePoint[] = []
  let cTotal = 0
  let cReturn = 0
  let cDD = 0
  let cCost = 0
  for (let i = 0; i < byStep.length; i += 1) {
    const r = byStep[i]
    if (!r) continue
    cTotal += r.total
    cReturn += r.returnComponent
    cDD += r.drawdownPenalty
    cCost += r.costPenalty
    out.push({
      step: i,
      cumulativeTotal: cTotal,
      cumulativeReturn: cReturn,
      cumulativeDrawdownPenalty: cDD,
      cumulativeCostPenalty: cCost,
    })
  }
  return out
}

function mergeOverlays(
  a: Record<string, SMCOverlay>,
  b: Record<string, SMCOverlay>,
): Record<string, SMCOverlay> {
  const out: Record<string, SMCOverlay> = {}
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const k of keys) {
    const oa = a[k]
    const ob = b[k]
    if (oa && !ob) {
      out[k] = oa
      continue
    }
    if (ob && !oa) {
      out[k] = ob
      continue
    }
    if (!oa || !ob) continue
    out[k] = {
      swings: [...oa.swings, ...ob.swings].sort(byBarIndexThenTime),
      zigzag: [...oa.zigzag, ...ob.zigzag].sort(byBarIndexThenTime),
      fvgs: [...oa.fvgs, ...ob.fvgs].sort((x, y) => x.from.localeCompare(y.from)),
      obs: [...oa.obs, ...ob.obs].sort((x, y) => x.from.localeCompare(y.from)),
      breaks: [...oa.breaks, ...ob.breaks].sort((x, y) => x.time.localeCompare(y.time)),
    }
  }
  return out
}

function byBarIndexThenTime(
  x: { barIndex: number; time: string },
  y: { barIndex: number; time: string },
): number {
  if (x.barIndex !== y.barIndex) return x.barIndex - y.barIndex
  return x.time.localeCompare(y.time)
}
