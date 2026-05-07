/**
 * 格式化 helpers — 一律於進入 i18n / 圖表前完成數字格式化，
 * 避免 i18next 端做 locale-dependent 處理造成跨機差異。
 *
 * 預設 locale 為 en-US（與後端 trajectory.csv 一致），
 * 若使用者偏好 zh-TW 顯示，由呼叫端覆寫 options.locale。
 */

export interface NumberFormatOptions {
  fractionDigits?: number
  locale?: string
  /** 強制顯示正負號（如 +1.23） */
  signDisplay?: 'auto' | 'never' | 'always' | 'exceptZero'
}

const DEFAULT_LOCALE = 'en-US'

export function formatNumber(value: number, opts: NumberFormatOptions = {}): string {
  if (!Number.isFinite(value)) return '—'
  const fractionDigits = opts.fractionDigits ?? 2
  const signDisplay = opts.signDisplay ?? 'auto'
  return new Intl.NumberFormat(opts.locale ?? DEFAULT_LOCALE, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay,
  }).format(value)
}

export function formatUSD(value: number, opts: NumberFormatOptions = {}): string {
  if (!Number.isFinite(value)) return '—'
  const fractionDigits = opts.fractionDigits ?? 2
  return new Intl.NumberFormat(opts.locale ?? DEFAULT_LOCALE, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)
}

/** value 為小數（0.0523 = 5.23%）；signDisplay 預設 'exceptZero'。 */
export function formatPercent(value: number, opts: NumberFormatOptions = {}): string {
  if (!Number.isFinite(value)) return '—'
  const fractionDigits = opts.fractionDigits ?? 2
  return new Intl.NumberFormat(opts.locale ?? DEFAULT_LOCALE, {
    style: 'percent',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: opts.signDisplay ?? 'exceptZero',
  }).format(value)
}

/** Parse ISO date or timestamp string 為 yyyy-mm-dd（穩定、locale-independent）。 */
export function formatDate(input: string | Date): string {
  const date = typeof input === 'string' ? new Date(input) : input
  if (Number.isNaN(date.getTime())) return '—'
  const yyyy = date.getUTCFullYear()
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(date.getUTCDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

export function formatDateTime(input: string | Date, locale: string = DEFAULT_LOCALE): string {
  const date = typeof input === 'string' ? new Date(input) : input
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(date)
}

/** 大數字縮寫：1234567 → 1.23M */
export function formatCompact(value: number, opts: NumberFormatOptions = {}): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat(opts.locale ?? DEFAULT_LOCALE, {
    notation: 'compact',
    maximumFractionDigits: opts.fractionDigits ?? 2,
  }).format(value)
}
