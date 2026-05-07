import { describe, expect, it } from 'vitest'

import {
  formatCompact,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatUSD,
} from '@/utils/format'

describe('formatNumber', () => {
  it('formats with default 2 fraction digits', () => {
    expect(formatNumber(1234.5678)).toBe('1,234.57')
  })

  it('respects custom fractionDigits', () => {
    expect(formatNumber(0.123456, { fractionDigits: 4 })).toBe('0.1235')
  })

  it('returns em dash for non-finite', () => {
    expect(formatNumber(NaN)).toBe('—')
    expect(formatNumber(Infinity)).toBe('—')
  })

  it('shows sign when signDisplay=always', () => {
    expect(formatNumber(5, { signDisplay: 'always' })).toBe('+5.00')
  })
})

describe('formatUSD', () => {
  it('formats positive amount', () => {
    expect(formatUSD(1234.5)).toBe('$1,234.50')
  })

  it('formats negative amount', () => {
    expect(formatUSD(-1234.5)).toBe('-$1,234.50')
  })
})

describe('formatPercent', () => {
  it('formats decimal as percentage with sign', () => {
    expect(formatPercent(0.0523)).toBe('+5.23%')
  })

  it('shows minus on negative', () => {
    expect(formatPercent(-0.1)).toBe('-10.00%')
  })

  it('handles zero without sign', () => {
    expect(formatPercent(0)).toBe('0.00%')
  })
})

describe('formatDate', () => {
  it('returns YYYY-MM-DD in UTC', () => {
    expect(formatDate('2024-01-02T15:30:00Z')).toBe('2024-01-02')
  })

  it('returns em dash for invalid input', () => {
    expect(formatDate('not-a-date')).toBe('—')
  })
})

describe('formatDateTime', () => {
  it('produces a stable UTC timestamp', () => {
    const out = formatDateTime('2024-01-02T15:30:45Z')
    expect(out).toContain('2024')
    expect(out).toContain('15:30:45')
  })
})

describe('formatCompact', () => {
  it('compacts large numbers', () => {
    expect(formatCompact(1_500_000)).toBe('1.5M')
  })
})
