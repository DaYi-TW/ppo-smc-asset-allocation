/**
 * Feature 010 T039 — DataLagBadge tests (FR-022 / SC-003).
 *
 * 4 個 cases：
 *   - dataLagDays=null → 「Live tracking 尚未啟動」
 *   - dataLagDays=0    → 「最新」
 *   - dataLagDays=1    → 「1 天前」
 *   - dataLagDays=7    → 「7 天前」
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DataLagBadge } from '@/components/overview/DataLagBadge'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'

function withI18n(node: React.ReactNode) {
  return <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
}

describe('DataLagBadge', () => {
  it('renders not-started when dataLagDays is null', () => {
    render(withI18n(<DataLagBadge dataLagDays={null} />))
    const el = screen.getByTestId('data-lag-badge')
    expect(el.textContent).toMatch(/尚未啟動|not started|Live tracking/i)
  })

  it('renders fresh when dataLagDays is 0', () => {
    render(withI18n(<DataLagBadge dataLagDays={0} />))
    const el = screen.getByTestId('data-lag-badge')
    expect(el.textContent).toMatch(/最新|fresh/i)
  })

  it('renders N days ago when dataLagDays > 0 (warning tone <=2)', () => {
    render(withI18n(<DataLagBadge dataLagDays={1} />))
    const el = screen.getByTestId('data-lag-badge')
    expect(el.textContent).toContain('1')
    expect(el.className).toContain('warning')
  })

  it('renders danger tone when dataLagDays > 2', () => {
    render(withI18n(<DataLagBadge dataLagDays={7} />))
    const el = screen.getByTestId('data-lag-badge')
    expect(el.textContent).toContain('7')
    expect(el.className).toContain('danger')
  })
})
