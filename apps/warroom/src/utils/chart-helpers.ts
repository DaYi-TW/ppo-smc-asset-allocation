/**
 * Chart helper functions — 純函式，無 DOM/Recharts 依賴，方便單元測試。
 *
 * - clamp：界定數值範圍。
 * - buildSMCMarkers：從 trajectory frames 萃取 SMC 訊號為 marker list。
 * - computeDrawdownSeries：從 NAV 序列計算 high-water mark 與 drawdown%。
 * - normaliseWeightFrames：將 7 維 perAsset 攤平為 stacked area chart 點陣。
 */

import type { SMCMarker, SMCMarkerKind } from '@/viewmodels/smc'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min
  return Math.min(Math.max(value, min), max)
}

export interface DrawdownPoint {
  timestamp: string
  nav: number
  highWaterMark: number
  drawdownPct: number
}

export function computeDrawdownSeries(
  frames: ReadonlyArray<Pick<TrajectoryFrame, 'timestamp' | 'nav'>>,
): DrawdownPoint[] {
  let peak = -Infinity
  return frames.map((f) => {
    if (f.nav > peak) peak = f.nav
    const dd = peak > 0 ? (f.nav - peak) / peak : 0
    return {
      timestamp: f.timestamp,
      nav: f.nav,
      highWaterMark: peak,
      drawdownPct: dd,
    }
  })
}

function bosKind(value: -1 | 0 | 1): SMCMarkerKind | null {
  if (value === 1) return 'BOS_BULL'
  if (value === -1) return 'BOS_BEAR'
  return null
}

function chochKind(value: -1 | 0 | 1): SMCMarkerKind | null {
  if (value === 1) return 'CHOCH_BULL'
  if (value === -1) return 'CHOCH_BEAR'
  return null
}

/**
 * 從 trajectory frames 萃取 SMC marker。
 * BOS/CHoCh 直接用 frame 訊號；FVG/OB 由距離判定（距離≈0 視為觸發）。
 *
 * 此函式為前端 fallback：完整 marker 應由 backend 已計算好附在 episode response。
 */
export function buildSMCMarkers(frames: ReadonlyArray<TrajectoryFrame>): SMCMarker[] {
  const markers: SMCMarker[] = []
  for (const frame of frames) {
    const { smcSignals: s, ohlcv, timestamp } = frame
    const bos = bosKind(s.bos)
    if (bos) {
      markers.push({
        id: `${timestamp}-${bos}`,
        kind: bos,
        timestamp,
        price: ohlcv.close,
        active: true,
        description: bos === 'BOS_BULL' ? 'Bullish break of structure' : 'Bearish break of structure',
        rule: 'close beyond prior swing',
      })
    }
    const ch = chochKind(s.choch)
    if (ch) {
      markers.push({
        id: `${timestamp}-${ch}`,
        kind: ch,
        timestamp,
        price: ohlcv.close,
        active: true,
        description: ch === 'CHOCH_BULL' ? 'Bullish change of character' : 'Bearish change of character',
        rule: 'first counter-trend break after BOS',
      })
    }
    if (s.obTouching) {
      markers.push({
        id: `${timestamp}-OB`,
        kind: 'OB',
        timestamp,
        rangeStart: { time: timestamp, price: ohlcv.low },
        rangeEnd: { time: timestamp, price: ohlcv.high },
        active: true,
        description: 'Price touched active order block',
        rule: 'distance/ATR ≈ 0',
      })
    }
  }
  return markers
}

export interface WeightStackPoint {
  timestamp: string
  step: number
  cash: number
  riskOff: number
  riskOn: number
  [asset: string]: number | string
}

/** 攤平成 stacked area chart 可消費的格式；保留 cash/riskOff/riskOn 三層 + per-asset 細項。 */
export function buildWeightStackPoints(
  frames: ReadonlyArray<TrajectoryFrame>,
): WeightStackPoint[] {
  return frames.map((frame) => {
    const point: WeightStackPoint = {
      timestamp: frame.timestamp,
      step: frame.step,
      cash: frame.weights.cash,
      riskOff: frame.weights.riskOff,
      riskOn: frame.weights.riskOn,
    }
    for (const [asset, weight] of Object.entries(frame.weights.perAsset)) {
      point[asset] = weight
    }
    return point
  })
}

/** Bisect — 給定 timestamp，回傳最接近的 frame index（O(log n)）。 */
export function findFrameIndex(
  frames: ReadonlyArray<Pick<TrajectoryFrame, 'timestamp'>>,
  timestamp: string,
): number {
  let lo = 0
  let hi = frames.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    const cur = frames[mid]?.timestamp ?? ''
    if (cur < timestamp) lo = mid + 1
    else hi = mid
  }
  return lo
}
