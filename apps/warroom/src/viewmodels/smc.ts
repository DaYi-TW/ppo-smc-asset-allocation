/**
 * SMC 訊號與圖上標記 — 對應 data-model.md §4。
 *
 * 兩種尺度：
 *  - SMCSignals：單一 frame 的瞬時觀測（與 trajectory 對齊）。
 *  - SMCMarker：跨 trajectory 萃取出的可繪製事件（K 線圖 overlay 用）。
 */

export interface SMCSignals {
  /** -1 看跌結構破壞、0 無、1 看漲結構破壞 */
  bos: -1 | 0 | 1
  /** Change of Character；-1 看跌、0 無、1 看漲 */
  choch: -1 | 0 | 1
  /** 至最近 unfilled FVG 的距離（價格比例）；無 FVG 時為 NaN */
  fvgDistancePct: number
  /** 當下價格是否接觸 active Order Block */
  obTouching: boolean
  /** 至最近 OB 的距離 / ATR；無 OB 時為 NaN */
  obDistanceRatio: number
}

export type SMCMarkerKind =
  | 'BOS_BULL'
  | 'BOS_BEAR'
  | 'CHOCH_BULL'
  | 'CHOCH_BEAR'
  | 'FVG'
  | 'OB'

export interface SMCMarkerRange {
  time: string
  price: number
}

/** Invariants:
 *  - BOS/CHoCh kind ⇒ 必有 price，無 rangeStart/rangeEnd
 *  - FVG/OB kind     ⇒ 必有 rangeStart 與 rangeEnd
 */
export interface SMCMarker {
  id: string
  kind: SMCMarkerKind
  timestamp: string
  price?: number
  rangeStart?: SMCMarkerRange
  rangeEnd?: SMCMarkerRange
  active: boolean
  description: string
  rule: string
}

/* ========== Structural overlay (TradingView-like) ========== */

export interface SwingPoint {
  /** ISO date "YYYY-MM-DD" */
  time: string
  price: number
  kind: 'high' | 'low'
  /** 在原 OHLC 序列的 bar index — 排序用 */
  barIndex: number
}

export interface FVGZone {
  /** 形成日（含） */
  from: string
  /** 填補日；未填補則延伸到序列尾 */
  to: string
  top: number
  bottom: number
  direction: 'bullish' | 'bearish'
  filled: boolean
}

export interface OBZone {
  from: string
  to: string
  top: number
  bottom: number
  direction: 'bullish' | 'bearish'
  invalidated: boolean
}

export interface StructureBreak {
  /** 突破發生日 */
  time: string
  /** 被突破的 swing 所在日期 — 破線從這裡畫到 time */
  anchorTime: string
  /** 被突破的 swing 價格（畫水平線用） */
  price: number
  /** 突破當日的 close（label 標位置用） */
  breakClose: number
  kind: 'BOS_BULL' | 'BOS_BEAR' | 'CHOCH_BULL' | 'CHOCH_BEAR'
}

/** 單檔資產的完整結構化 SMC 視覺資料。 */
export interface SMCOverlay {
  swings: SwingPoint[]
  /** 高低點交替的折線，按 barIndex 排序 — zigzag 用。 */
  zigzag: SwingPoint[]
  fvgs: FVGZone[]
  obs: OBZone[]
  breaks: StructureBreak[]
}
