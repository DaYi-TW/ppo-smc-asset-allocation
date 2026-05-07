/**
 * PolicyPicker component test — 走 MSW handlers 取真實 fixture。
 *
 * 驗證：
 *  1. 載入後三個 policy 選項都出現。
 *  2. 變更選項會 callback `onChange` 帶 policyId。
 *  3. 預設值優先順序：value prop > active=true policy > 第一筆。
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PolicyPicker } from '@/components/panels/PolicyPicker'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('PolicyPicker', () => {
  it('renders three policies from MSW fixture', async () => {
    const onChange = vi.fn()
    renderWithClient(<PolicyPicker value={undefined} onChange={onChange} />)

    const select = await waitFor(() => screen.getByRole('combobox'))
    const options = Array.from(select.querySelectorAll('option'))
    expect(options).toHaveLength(3)
    expect(options.map((o) => o.value)).toEqual([
      'ppo-smc-500k',
      'ppo-no-smc-500k',
      'nvda-buy-and-hold',
    ])
  })

  it('calls onChange when user picks a different policy', async () => {
    const onChange = vi.fn()
    renderWithClient(<PolicyPicker value="ppo-smc-500k" onChange={onChange} />)

    const select = await waitFor(() => screen.getByRole('combobox'))
    await userEvent.selectOptions(select, 'ppo-no-smc-500k')
    expect(onChange).toHaveBeenCalledWith('ppo-no-smc-500k')
  })

  it('defaults to active policy when value prop is undefined', async () => {
    const onChange = vi.fn()
    renderWithClient(<PolicyPicker value={undefined} onChange={onChange} />)

    const select = await waitFor(() => screen.getByRole('combobox')) as HTMLSelectElement
    expect(select.value).toBe('ppo-smc-500k')
  })
})
