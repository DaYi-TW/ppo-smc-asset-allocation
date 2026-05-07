/**
 * Runtime chart theme — Recharts / lightweight-charts 不支援 CSS variable，
 * 必須在 render 時讀 :root 的 computed style。
 *
 * 對應 contracts/theme-tokens.md「圖表元件主題注入」章節。
 */

import { assetColors, smcMarkerColors } from './tokens'

export interface ChartTheme {
  background: string
  text: string
  grid: string
  border: string
  primary: string
  success: string
  danger: string
  warn: string
  info: string
  navLine: string
  drawdown: string
  asset: typeof assetColors
  smc: typeof smcMarkerColors
}

function readVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export function getChartTheme(): ChartTheme {
  const isDark =
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark')

  return {
    background: readVar('--color-bg-surface', isDark ? '#1E293B' : '#F8FAFC'),
    text: readVar('--color-text-primary', isDark ? '#F1F5F9' : '#0F172A'),
    grid: readVar('--color-border-default', isDark ? '#334155' : '#E2E8F0'),
    border: readVar('--color-border-strong', isDark ? '#475569' : '#CBD5E1'),
    primary: readVar('--color-primary-default', isDark ? '#3B82F6' : '#2563EB'),
    success: readVar('--color-success', isDark ? '#22C55E' : '#16A34A'),
    danger: readVar('--color-danger', isDark ? '#EF4444' : '#DC2626'),
    warn: readVar('--color-warn', isDark ? '#FBBF24' : '#F59E0B'),
    info: readVar('--color-info', isDark ? '#38BDF8' : '#0EA5E9'),
    // NAV line 強制黑/白以與 drawdown 紅色對比
    navLine: isDark ? '#F1F5F9' : '#0F172A',
    drawdown: '#DC2626',
    asset: assetColors,
    smc: smcMarkerColors,
  }
}
