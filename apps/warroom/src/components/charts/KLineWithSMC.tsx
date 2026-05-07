/**
 * KLineWithSMC — lightweight-charts K 線 + TradingView-like SMC overlay。
 *
 * - 主圖：addCandlestickSeries(ohlcv)，含 zoom/pan（lwc 內建）。
 * - SMC：透過 SMCOverlayPrimitive 自畫 canvas（FVG/OB 矩形、BOS/CHoCh 破線、Swing zigzag）。
 *   prop `visible` 控制 4 個結構獨立 toggle + activeOnly + zigzag。
 * - 主題切換時 chart 透過 applyOptions() 即時更新顏色（lwc 不讀 CSS var）。
 */

import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'

import { useTimeRange } from '@/contexts/TimeRangeContext'
import { getChartTheme } from '@/theme/getChartTheme'
import type { SMCOverlay } from '@/viewmodels/smc'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

import {
  DEFAULT_SMC_VISIBLE,
  SMCOverlayPrimitive,
  type SMCVisibleConfig,
} from './smcOverlayPrimitive'

export interface KLineWithSMCProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
  /** 顯示哪一檔資產的 K 線。fixture 需含 ohlcvByAsset；缺時 fallback 至 frame.ohlcv。 */
  selectedAsset?: string | undefined
  /** 對應 selectedAsset 的 SMC overlay；缺則 chart 不畫結構標記。 */
  overlay?: SMCOverlay | undefined
  /** 4 個結構 + activeOnly + zigzag 開關；缺省為全開 active-only。 */
  visible?: SMCVisibleConfig
}

interface CandleDatum {
  time: Time
  open: number
  high: number
  low: number
  close: number
}

function toCandle(frame: TrajectoryFrame, selectedAsset?: string): CandleDatum {
  const o = (selectedAsset && frame.ohlcvByAsset?.[selectedAsset]) || frame.ohlcv
  return {
    time: frame.timestamp as Time,
    open: o.open,
    high: o.high,
    low: o.low,
    close: o.close,
  }
}

const EMPTY_OVERLAY: SMCOverlay = { swings: [], zigzag: [], fvgs: [], obs: [], breaks: [] }

export function KLineWithSMC({
  frames,
  height = 360,
  selectedAsset,
  overlay,
  visible = DEFAULT_SMC_VISIBLE,
}: KLineWithSMCProps) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const primitiveRef = useRef<SMCOverlayPrimitive | null>(null)
  const { range } = useTimeRange(frames.length)

  const candles = useMemo(
    () => frames.map((f) => toCandle(f, selectedAsset)),
    [frames, selectedAsset],
  )
  const overlaySafe = overlay ?? EMPTY_OVERLAY

  // Init chart once
  useEffect(() => {
    if (!containerRef.current) return
    const theme = getChartTheme()
    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: theme.background },
        textColor: theme.text,
      },
      grid: {
        vertLines: { color: theme.grid },
        horzLines: { color: theme.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: theme.border },
      timeScale: { borderColor: theme.border, timeVisible: true },
    })
    const series = chart.addCandlestickSeries({
      upColor: theme.success,
      downColor: theme.danger,
      wickUpColor: theme.success,
      wickDownColor: theme.danger,
      borderVisible: false,
    })
    chartRef.current = chart
    seriesRef.current = series

    // attach SMC primitive once
    const prim = new SMCOverlayPrimitive(EMPTY_OVERLAY, DEFAULT_SMC_VISIBLE, theme)
    series.attachPrimitive(prim)
    primitiveRef.current = prim

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.resize(containerRef.current.clientWidth, height)
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      const s = seriesRef.current
      const p = primitiveRef.current
      if (s && p) s.detachPrimitive(p)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      primitiveRef.current = null
    }
  }, [height])

  // 餵 candles
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    series.setData(candles)
  }, [candles])

  // overlay / visible 變化 → 更新 primitive
  useEffect(() => {
    const prim = primitiveRef.current
    const chart = chartRef.current
    if (!prim || !chart) return
    prim.setOverlay(overlaySafe)
    prim.setVisible(visible)
    chart.applyOptions({}) // 觸發重畫
  }, [overlaySafe, visible])

  // 同步 timeline scrubber → lwc visible range
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || candles.length === 0) return
    const from = Math.max(0, range.start)
    const to = Math.max(from, Math.min(range.end - 1, candles.length - 1))
    chart.timeScale().setVisibleLogicalRange({ from, to })
  }, [range.start, range.end, candles.length])

  // 主題切換
  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const apply = () => {
      const theme = getChartTheme()
      chartRef.current?.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: theme.background },
          textColor: theme.text,
        },
        grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      })
      seriesRef.current?.applyOptions({
        upColor: theme.success,
        downColor: theme.danger,
        wickUpColor: theme.success,
        wickDownColor: theme.danger,
      })
      primitiveRef.current?.setTheme(theme)
    }
    const obs = new MutationObserver(apply)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  return (
    <div
      role="figure"
      aria-label={t('trajectory.kline.title')}
      data-overlay-fvg={overlaySafe.fvgs.length}
      data-overlay-ob={overlaySafe.obs.length}
      data-overlay-breaks={overlaySafe.breaks.length}
      ref={containerRef}
      style={{ width: '100%', height }}
    />
  )
}
