/**
 * SMC Overlay primitive — TradingView-like 結構標記。
 *
 * 透過 lightweight-charts v4 ISeriesPrimitive 自畫 canvas：
 *   - FVG / OB：半透明矩形（filled / invalidated 後變灰、半透明更低）
 *   - BOS / CHoCh：水平虛線從 anchor swing 拉到 break bar，文字標籤
 *   - Swing zigzag：HH/HL/LH/LL 折線
 *
 * 座標轉換：x = chart.timeScale().timeToCoordinate(time)
 *           y = series.priceToCoordinate(price)
 * 任一回 null 表示該時點 / 價位在可視範圍外，跳過該段。
 */

import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts'

import type { ChartTheme } from '@/theme/getChartTheme'
import type {
  FVGZone,
  OBZone,
  SMCOverlay,
  StructureBreak,
} from '@/viewmodels/smc'

export interface SMCVisibleConfig {
  bos: boolean
  choch: boolean
  fvg: boolean
  ob: boolean
  /** 預設 true — 只畫 active（未填 FVG / 未失效 OB / 全 swings + breaks）。
   *  false 時畫全部歷史。 */
  activeOnly: boolean
  /** Swing zigzag 折線 — 與 4 個結構獨立。 */
  zigzag: boolean
}

export const DEFAULT_SMC_VISIBLE: SMCVisibleConfig = {
  bos: true,
  choch: true,
  fvg: true,
  ob: true,
  // 預設只顯示 active（未填 FVG / 未失效 OB）— 真實 OOS overlay 多數 zone
  // 已 invalidated/filled，全畫會疊出大量噪音橫條；使用者按 History 鈕切回全歷史。
  activeOnly: true,
  zigzag: true,
}

const FVG_BULL_COLOR = 'rgba(34, 197, 94, 0.18)'
const FVG_BEAR_COLOR = 'rgba(239, 68, 68, 0.18)'
const FVG_BULL_FILLED = 'rgba(34, 197, 94, 0.06)'
const FVG_BEAR_FILLED = 'rgba(239, 68, 68, 0.06)'
const FVG_BORDER_BULL = 'rgba(34, 197, 94, 0.5)'
const FVG_BORDER_BEAR = 'rgba(239, 68, 68, 0.5)'

const OB_BULL_COLOR = 'rgba(59, 130, 246, 0.18)'
const OB_BEAR_COLOR = 'rgba(249, 115, 22, 0.18)'
const OB_BULL_INVALID = 'rgba(59, 130, 246, 0.05)'
const OB_BEAR_INVALID = 'rgba(249, 115, 22, 0.05)'
const OB_BORDER_BULL = 'rgba(59, 130, 246, 0.6)'
const OB_BORDER_BEAR = 'rgba(249, 115, 22, 0.6)'

// CHoCh 用獨立色系，避免與 BOS（success/danger）重疊時無法區分
// 紫色＝反轉訊號（trend change of character）
const CHOCH_BULL_COLOR = 'rgb(168, 85, 247)' // violet-500
const CHOCH_BEAR_COLOR = 'rgb(217, 70, 239)' // fuchsia-500

class SMCRenderer implements ISeriesPrimitivePaneRenderer {
  constructor(
    private overlay: SMCOverlay,
    private visible: SMCVisibleConfig,
    private chart: IChartApi,
    private series: ISeriesApi<SeriesType>,
    private theme: ChartTheme,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const { context: ctx, bitmapSize, mediaSize } = scope
      const dpr = bitmapSize.width / mediaSize.width
      ctx.save()
      ctx.scale(dpr, dpr)

      // Draw order: rectangles (background) → zigzag → break lines (foreground)
      if (this.visible.fvg) this.drawFVGs(ctx)
      if (this.visible.ob) this.drawOBs(ctx)
      if (this.visible.zigzag) this.drawZigzag(ctx)
      this.drawBreaks(ctx)

      ctx.restore()
    })
  }

  private timeX(time: string): number | null {
    return this.chart.timeScale().timeToCoordinate(time as Time)
  }

  private priceY(price: number): number | null {
    return this.series.priceToCoordinate(price)
  }

  private drawFVGs(ctx: CanvasRenderingContext2D) {
    for (const z of this.overlay.fvgs) {
      if (this.visible.activeOnly && z.filled) continue
      this.drawZone(ctx, z, {
        fillBull: FVG_BULL_COLOR,
        fillBear: FVG_BEAR_COLOR,
        fillBullDim: FVG_BULL_FILLED,
        fillBearDim: FVG_BEAR_FILLED,
        borderBull: FVG_BORDER_BULL,
        borderBear: FVG_BORDER_BEAR,
        dim: z.filled,
      })
    }
  }

  private drawOBs(ctx: CanvasRenderingContext2D) {
    for (const z of this.overlay.obs) {
      if (this.visible.activeOnly && z.invalidated) continue
      this.drawZone(ctx, z, {
        fillBull: OB_BULL_COLOR,
        fillBear: OB_BEAR_COLOR,
        fillBullDim: OB_BULL_INVALID,
        fillBearDim: OB_BEAR_INVALID,
        borderBull: OB_BORDER_BULL,
        borderBear: OB_BORDER_BEAR,
        dim: z.invalidated,
      })
    }
  }

  private drawZone(
    ctx: CanvasRenderingContext2D,
    z: FVGZone | OBZone,
    palette: {
      fillBull: string
      fillBear: string
      fillBullDim: string
      fillBearDim: string
      borderBull: string
      borderBear: string
      dim: boolean
    },
  ) {
    const x1 = this.timeX(z.from)
    const x2 = this.timeX(z.to)
    const yTop = this.priceY(z.top)
    const yBot = this.priceY(z.bottom)
    if (x1 == null || x2 == null || yTop == null || yBot == null) return
    const left = Math.min(x1, x2)
    const right = Math.max(x1, x2)
    const top = Math.min(yTop, yBot)
    const h = Math.abs(yBot - yTop)
    const w = Math.max(1, right - left)
    const isBull = z.direction === 'bullish'
    const fill = palette.dim
      ? isBull
        ? palette.fillBullDim
        : palette.fillBearDim
      : isBull
      ? palette.fillBull
      : palette.fillBear
    const border = isBull ? palette.borderBull : palette.borderBear
    ctx.fillStyle = fill
    ctx.fillRect(left, top, w, h)
    ctx.strokeStyle = border
    ctx.lineWidth = palette.dim ? 0.5 : 1
    ctx.setLineDash(palette.dim ? [3, 3] : [])
    ctx.strokeRect(left, top, w, h)
    ctx.setLineDash([])
  }

  private drawZigzag(ctx: CanvasRenderingContext2D) {
    const pts = this.overlay.zigzag
    if (pts.length < 2) return
    ctx.beginPath()
    ctx.lineWidth = 1
    ctx.strokeStyle = this.theme.text
    ctx.setLineDash([2, 4])
    let started = false
    for (const p of pts) {
      const x = this.timeX(p.time)
      const y = this.priceY(p.price)
      if (x == null || y == null) {
        started = false
        continue
      }
      if (!started) {
        ctx.moveTo(x, y)
        started = true
      } else {
        ctx.lineTo(x, y)
      }
    }
    ctx.stroke()
    ctx.setLineDash([])

    // 點標記
    for (const p of pts) {
      const x = this.timeX(p.time)
      const y = this.priceY(p.price)
      if (x == null || y == null) continue
      ctx.fillStyle = p.kind === 'high' ? this.theme.danger : this.theme.success
      ctx.beginPath()
      ctx.arc(x, y, 2.5, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  private drawBreaks(ctx: CanvasRenderingContext2D) {
    for (const b of this.overlay.breaks) {
      const isBOS = b.kind.startsWith('BOS')
      if (isBOS && !this.visible.bos) continue
      if (!isBOS && !this.visible.choch) continue
      this.drawBreak(ctx, b)
    }
  }

  private drawBreak(ctx: CanvasRenderingContext2D, b: StructureBreak) {
    const xAnchor = this.timeX(b.anchorTime)
    const xBreak = this.timeX(b.time)
    const y = this.priceY(b.price)
    if (xAnchor == null || xBreak == null || y == null) return
    const isBull = b.kind.endsWith('BULL')
    const isBOS = b.kind.startsWith('BOS')
    const color = isBOS
      ? isBull
        ? this.theme.success
        : this.theme.danger
      : isBull
      ? CHOCH_BULL_COLOR
      : CHOCH_BEAR_COLOR

    // 水平虛線 anchor → break
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.setLineDash(isBOS ? [4, 3] : [1, 3])
    ctx.beginPath()
    ctx.moveTo(xAnchor, y)
    ctx.lineTo(xBreak, y)
    ctx.stroke()
    ctx.setLineDash([])

    // 標籤（斷點正上 / 正下）
    const label = isBOS ? 'BOS' : 'CHoCh'
    ctx.font = '10px system-ui, sans-serif'
    ctx.fillStyle = color
    ctx.textBaseline = 'middle'
    const offY = isBull ? -8 : 8
    const labelX = (xAnchor + xBreak) / 2
    ctx.textAlign = 'center'
    ctx.fillText(label, labelX, y + offY)
  }
}

class SMCPaneView implements ISeriesPrimitivePaneView {
  constructor(
    private overlay: SMCOverlay,
    private visible: SMCVisibleConfig,
    private chart: IChartApi,
    private series: ISeriesApi<SeriesType>,
    private theme: ChartTheme,
  ) {}

  setData(overlay: SMCOverlay, visible: SMCVisibleConfig, theme: ChartTheme) {
    this.overlay = overlay
    this.visible = visible
    this.theme = theme
  }

  renderer(): ISeriesPrimitivePaneRenderer {
    return new SMCRenderer(this.overlay, this.visible, this.chart, this.series, this.theme)
  }
}

export class SMCOverlayPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null
  private series: ISeriesApi<SeriesType> | null = null
  private view: SMCPaneView | null = null

  constructor(
    private overlay: SMCOverlay,
    private visible: SMCVisibleConfig,
    private theme: ChartTheme,
  ) {}

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart
    this.series = param.series
    this.view = new SMCPaneView(
      this.overlay,
      this.visible,
      this.chart,
      this.series,
      this.theme,
    )
  }

  detached(): void {
    this.chart = null
    this.series = null
    this.view = null
  }

  updateAllViews(): void {
    this.view?.setData(this.overlay, this.visible, this.theme)
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return this.view ? [this.view] : []
  }

  setOverlay(overlay: SMCOverlay) {
    this.overlay = overlay
    this.updateAllViews()
  }

  setVisible(visible: SMCVisibleConfig) {
    this.visible = visible
    this.updateAllViews()
  }

  setTheme(theme: ChartTheme) {
    this.theme = theme
    this.updateAllViews()
  }
}
