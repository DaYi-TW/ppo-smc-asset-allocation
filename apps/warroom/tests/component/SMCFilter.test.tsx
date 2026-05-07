/**
 * SMCFilter component test — checkbox toggle 行為。
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SMCFilter } from '@/components/panels/SMCFilter'
import type { SMCMarkerKind } from '@/viewmodels/smc'
import { ALL_SMC_KINDS } from '@/viewmodels/smc-constants'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

describe('SMCFilter', () => {
  it('renders four checkbox groups (BOS/CHoCh/FVG/OB)', () => {
    const onChange = vi.fn()
    render(<SMCFilter value={new Set(ALL_SMC_KINDS)} onChange={onChange} />)
    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
  })

  it('all checkboxes are checked when value contains all kinds', () => {
    const onChange = vi.fn()
    render(<SMCFilter value={new Set(ALL_SMC_KINDS)} onChange={onChange} />)
    for (const cb of screen.getAllByRole('checkbox')) {
      expect(cb).toBeChecked()
    }
  })

  it('toggling BOS group removes BOS_BULL and BOS_BEAR via onChange', async () => {
    const onChange = vi.fn<[Set<SMCMarkerKind>], void>()
    render(<SMCFilter value={new Set(ALL_SMC_KINDS)} onChange={onChange} />)

    const bosCheckbox = screen.getAllByRole('checkbox')[0]!
    await userEvent.click(bosCheckbox)

    expect(onChange).toHaveBeenCalledTimes(1)
    const next = onChange.mock.calls[0]?.[0]
    expect(next?.has('BOS_BULL')).toBe(false)
    expect(next?.has('BOS_BEAR')).toBe(false)
    expect(next?.has('CHOCH_BULL')).toBe(true)
    expect(next?.has('FVG')).toBe(true)
    expect(next?.has('OB')).toBe(true)
  })

  it('toggling unchecked group adds both kinds', async () => {
    const onChange = vi.fn<[Set<SMCMarkerKind>], void>()
    const partial = new Set<SMCMarkerKind>(['CHOCH_BULL', 'CHOCH_BEAR', 'FVG', 'OB'])
    render(<SMCFilter value={partial} onChange={onChange} />)

    const bosCheckbox = screen.getAllByRole('checkbox')[0]!
    expect(bosCheckbox).not.toBeChecked()
    await userEvent.click(bosCheckbox)

    const next = onChange.mock.calls[0]?.[0]
    expect(next?.has('BOS_BULL')).toBe(true)
    expect(next?.has('BOS_BEAR')).toBe(true)
  })
})
