/**
 * csv-to-fixture script integration test — 跑一次 converter 並檢查 schema 合於 EpisodeDetailDto。
 */

import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, unlinkSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it, afterAll } from 'vitest'

const SCRIPT = resolve(__dirname, '../../scripts/csv-to-fixture.cjs')
const SAMPLE_CSV = resolve(__dirname, 'sample-trajectory.csv')
const OUT = resolve(__dirname, '__tmp_fixture.json')

afterAll(() => {
  if (existsSync(OUT)) unlinkSync(OUT)
})

describe('csv-to-fixture converter', () => {
  it('converts CSV → EpisodeDetail-shaped JSON with expected metrics', () => {
    execFileSync('node', [SCRIPT, SAMPLE_CSV, OUT, 'test-policy', 'v0.1.0'], {
      stdio: 'pipe',
    })

    expect(existsSync(OUT)).toBe(true)
    const detail = JSON.parse(readFileSync(OUT, 'utf8'))

    expect(detail.policyId).toBe('test-policy')
    expect(detail.policyVersion).toBe('v0.1.0')
    expect(detail.totalSteps).toBe(5)
    expect(detail.startDate).toBe('2024-01-02')
    expect(detail.endDate).toBe('2024-01-08')
    expect(detail.config.symbols).toEqual(['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT', 'CASH'])
    expect(detail.trajectoryInline).toHaveLength(5)

    const f0 = detail.trajectoryInline[0]
    expect(f0.timestamp).toBe('2024-01-02')
    expect(f0.step).toBe(0)
    expect(f0.nav).toBeCloseTo(100_000, 0)
    expect(f0.weights.perAsset.NVDA).toBeCloseTo(0.18, 5)
    expect(f0.weights.riskOn).toBeCloseTo(0.18 + 0.14 + 0.13, 5)
    expect(f0.weights.riskOff).toBeCloseTo(0.25 + 0.15, 5)
    expect(f0.weights.cash).toBeCloseTo(0.15, 5)
    expect(f0.ohlcv.close).toBeCloseTo(492.44, 2)

    expect(detail.totalReturn).toBeGreaterThan(0)
    expect(detail.rewardBreakdown.cumulative).toHaveLength(5)
    expect(detail.rewardBreakdown.byStep).toHaveLength(5)
  })
})
