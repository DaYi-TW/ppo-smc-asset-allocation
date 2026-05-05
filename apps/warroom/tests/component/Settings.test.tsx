/**
 * Settings page component test — 驗證偏好變更會寫入 localStorage 並 toggle <html>.dark。
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SettingsPage } from '@/pages/SettingsPage'
import { PREFERENCES_STORAGE_KEY } from '@/viewmodels/policy'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
}))

vi.mock('@/hooks/usePolicies', () => ({
  usePolicies: () => ({
    data: [
      {
        policyId: 'policy-a',
        policyVersion: 'v1',
        displayName: 'Policy A',
        trainedAt: '2024-01-01',
        trainingDataRange: { start: '2018-01-01', end: '2023-12-31' },
        configSummary: '',
        metrics: { sharpeRatio: 1, maxDrawdown: -0.1, cumulativeReturn: 0.2 },
        active: true,
      },
    ],
    isLoading: false,
  }),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>,
  )
}

describe('SettingsPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('persists language change to localStorage', () => {
    renderPage()
    const select = screen.getByLabelText('settings.language.label') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'en' } })
    const stored = JSON.parse(window.localStorage.getItem(PREFERENCES_STORAGE_KEY) ?? '{}')
    expect(stored.language).toBe('en')
  })

  it('toggles <html>.dark when theme changes to dark', () => {
    renderPage()
    const select = screen.getByLabelText('settings.theme.label') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'dark' } })
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('persists defaultPolicyId selection', () => {
    renderPage()
    const select = screen.getByLabelText('settings.defaultPolicy.label') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'policy-a' } })
    const stored = JSON.parse(window.localStorage.getItem(PREFERENCES_STORAGE_KEY) ?? '{}')
    expect(stored.defaultPolicyId).toBe('policy-a')
  })
})
