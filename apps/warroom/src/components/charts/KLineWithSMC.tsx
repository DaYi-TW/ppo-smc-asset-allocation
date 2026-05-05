/**
 * KLineWithSMC — lightweight-charts K 線 + SMC overlay。
 *
 * - 主圖：addCandlestickSeries(ohlcv)，含 zoom/pan（lwc 內建）。
 * - 標記：BOS/CHoCh 用 setMarkers()（上箭頭 = bull、下箭頭 = bear）。
 * - 區塊：FVG/OB 用 priceLines（簡化：用 createPriceLine 標出 active 區段邊界）。
 *
 * 主題切換時 chart 透過 applyOptions() 即時更新顏色（lwc 不讀 CSS var）。
 */

import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'

import { getChartTheme, type ChartTheme } from '@/theme/getChartTheme'
import { buildSMCMarkers } from '@/utils/chart-helpers'
import type { SMCMarker, SMCMarkerKind } from '@/viewmodels/smc'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

export interface KLineWithSMCProps {
  frames: ReadonlyArray<TrajectoryFrame>
  height?: number
  /** SMC marker kinds 顯隱控制（undefined = 全部顯示） */
  visibleKinds?: ReadonlySet<SMCMarkerKind>
}

interface CandleDatum {
  time: Time
  open: number
  high: number
  low: number
  close: number
}

function toCandle(frame: TrajectoryFrame): CandleDatum {
  return {
    time: frame.timestamp as Time,
    open: frame.ohlcv.open,
    high: frame.ohlcv.high,
    low: frame.ohlcv.low,
    close: frame.ohlcv.close,
  }
}

function markerToLwc(m: SMCMarker, theme: ChartTheme): SeriesMarker<Time> {
  switch (m.kind) {
    case 'BOS_BULL':
      return {
        time: m.timestamp as Time,
        position: 'belowBar',
        color: theme.success,
        shape: 'arrowUp',
        text: 'BOS',
      }
    case 'BOS_BEAR':
      return {
        time: m.timestamp as Time,
        position: 'aboveBar',
        color: theme.danger,
        shape: 'arrowDown',
        text: 'BOS',
      }
    case 'CHOCH_BULL':
      return {
        time: m.timestamp as Time,
        position: 'belowBar',
        color: theme.success,
        shape: 'circle',
        text: 'CHoCh',
      }
    case 'CHOCH_BEAR':
      return {
        time: m.timestamp as Time,
        position: 'aboveBar',
        color: theme.danger,
        shape: 'circle',
        text: 'CHoCh',
      }
    case 'FVG':
      return {
        time: m.timestamp as Time,
        position: 'inBar',
        color: theme.primary,
        shape: 'square',
        text: 'FVG',
      }
    case 'OB':
      return {
        time: m.timestamp as Time,
        position: 'inBar',
        color: theme.primary,
        shape: 'square',
        text: 'OB',
      }
  }
}

export function KLineWithSMC({ frames, height = 360, visibleKinds }: KLineWithSMCProps) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const candles = useMemo(() => frames.map(toCandle), [frames])
  const allMarkers = useMemo(() => buildSMCMarkers(frames), [frames])
  const filteredMarkers = useMemo(
    () => (visibleKinds ? allMarkers.filter((m) => visibleKinds.has(m.kind)) : allMarkers),
    [allMarkers, visibleKinds],
  )

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

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.resize(containerRef.current.clientWidth, height)
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  // Update data + markers
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    series.setData(candles)
    const theme = getChartTheme()
    series.setMarkers(filteredMarkers.map((m) => markerToLwc(m, theme)))
  }, [candles, filteredMarkers])

  // React to theme change via MutationObserver on <html class>
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
      seriesRef.current?.setMarkers(filteredMarkers.map((m) => markerToLwc(m, theme)))
    }
    const obs = new MutationObserver(apply)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [filteredMarkers])

  return (
    <div
      role="figure"
      aria-label={t('trajectory.kline.title')}
      data-marker-count={filteredMarkers.length}
      ref={containerRef}
      style={{ width: '100%', height }}
    />
  )
}
