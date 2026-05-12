/**
 * E2E — /decision：auto-pick episode → 切 step → 切 live 模式 → SSE 連線狀態變動。
 *
 * 009/010 後 EpisodePicker 仍在 page header，AppShell footer 加 locale/theme
 * select。改用 page-level label 過濾（「選擇 Episode」）+ main scope 避免歧義。
 */

import { expect, test } from '@playwright/test'

test.describe('Decision page', () => {
  test('renders observation/action/reward panels after default-episode load', async ({ page }) => {
    await page.goto('/#/decision')

    // EpisodePicker 應該自動填首筆
    await expect(page).toHaveURL(/episode=/, { timeout: 10_000 })

    await expect(
      page.getByRole('heading', { name: /觀測|Observation/i }),
    ).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: /動作|Action/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: /獎勵|Reward/i })).toBeVisible()
  })

  test('switching to live mode shows SSE status indicator', async ({ page }) => {
    await page.goto('/#/decision')
    await expect(page).toHaveURL(/episode=/, { timeout: 10_000 })

    // live radio button — DecisionPage 用 <input type="radio" name="decision-mode">
    await page.getByRole('radio', { name: 'live' }).check()

    // role=status block 顯示「SSE: ...」
    await expect(page.getByRole('status')).toBeVisible()
    await expect(page).toHaveURL(/mode=live/)
  })

  test('step slider updates URL', async ({ page }) => {
    await page.goto('/#/decision')
    await expect(page).toHaveURL(/episode=/, { timeout: 10_000 })

    // 等 detail loaded（observation 出現代表 frame 已存在 → slider 也存在）
    await expect(
      page.getByRole('heading', { name: /觀測|Observation/i }),
    ).toBeVisible({ timeout: 15_000 })

    const slider = page.getByLabel('step')
    await slider.fill('5')
    await expect(page).toHaveURL(/step=5/)
  })
})
