/**
 * 設計 Token — 對應 contracts/theme-tokens.md。
 *
 * 兩份完整 palette（light / dark），加上不隨主題變色的圖表 palette。
 * 所有 chart 元件透過 getChartTheme() 讀 CSS variable，避免硬編碼。
 */

export type ThemeMode = 'light' | 'dark'

export interface ColorTokens {
  bgBase: string
  bgSurface: string
  bgElevated: string
  textPrimary: string
  textSecondary: string
  textMuted: string
  borderDefault: string
  borderStrong: string
  primaryDefault: string
  primaryHover: string
  success: string
  danger: string
  warn: string
  info: string
  choch: string
  obDemand: string
  obSupply: string
  cash: string
}

export const lightColors: ColorTokens = {
  bgBase: '#FFFFFF',
  bgSurface: '#F8FAFC',
  bgElevated: '#FFFFFF',
  textPrimary: '#0F172A',
  textSecondary: '#475569',
  textMuted: '#94A3B8',
  borderDefault: '#E2E8F0',
  borderStrong: '#CBD5E1',
  primaryDefault: '#2563EB',
  primaryHover: '#1D4ED8',
  success: '#16A34A',
  danger: '#DC2626',
  warn: '#F59E0B',
  info: '#0EA5E9',
  choch: '#EAB308',
  obDemand: '#10B981',
  obSupply: '#EF4444',
  cash: '#64748B',
}

export const darkColors: ColorTokens = {
  bgBase: '#0F172A',
  bgSurface: '#1E293B',
  bgElevated: '#334155',
  textPrimary: '#F1F5F9',
  textSecondary: '#CBD5E1',
  textMuted: '#64748B',
  borderDefault: '#334155',
  borderStrong: '#475569',
  primaryDefault: '#3B82F6',
  primaryHover: '#2563EB',
  success: '#22C55E',
  danger: '#EF4444',
  warn: '#FBBF24',
  info: '#38BDF8',
  choch: '#FACC15',
  obDemand: '#34D399',
  obSupply: '#F87171',
  cash: '#94A3B8',
}

/** 圖表專用 — 不隨主題變色（資產品牌色為硬約定）。 */
export const assetColors = {
  NVDA: '#76B900',
  AMD: '#ED1C24',
  TSM: '#CC0000',
  MU: '#B71F31',
  GLD: '#FFD700',
  TLT: '#1E40AF',
  CASH: '#64748B',
} as const

export type AssetSymbol = keyof typeof assetColors

/** SMC marker 顏色（亮暗共用） */
export const smcMarkerColors = {
  BOS_BULL: '#22C55E',
  BOS_BEAR: '#EF4444',
  CHOCH_BULL: '#FACC15',
  CHOCH_BEAR: '#F59E0B',
  FVG: '#38BDF8',
  OB_DEMAND: '#10B981',
  OB_SUPPLY: '#EF4444',
} as const

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  '2xl': '32px',
} as const

export const radius = {
  none: '0',
  sm: '4px',
  md: '6px',
  lg: '8px',
  xl: '12px',
  full: '9999px',
} as const

export const fontFamily = {
  sans: "'Inter', 'Noto Sans TC', system-ui, -apple-system, sans-serif",
  mono: "'JetBrains Mono', 'Consolas', ui-monospace, monospace",
} as const

export const fontSize = {
  xs: '0.75rem',
  sm: '0.875rem',
  base: '1rem',
  lg: '1.125rem',
  xl: '1.25rem',
  '2xl': '1.5rem',
  '3xl': '1.875rem',
} as const

export const shadow = {
  none: 'none',
  sm: '0 1px 2px rgba(15, 23, 42, 0.08)',
  md: '0 4px 6px rgba(15, 23, 42, 0.10)',
  lg: '0 10px 15px rgba(15, 23, 42, 0.12)',
} as const

export const zIndex = {
  base: 0,
  raised: 10,
  dropdown: 100,
  sticky: 200,
  modal: 1000,
  toast: 2000,
} as const

export function getColorTokens(mode: ThemeMode): ColorTokens {
  return mode === 'dark' ? darkColors : lightColors
}
