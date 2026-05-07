/**
 * E2E — /decision：選 episode → 切 step → 切到 live 模式 → SSE 連線狀態變動。
 */

import { expect, test } from '@playwright/test'

test.describe('Decision page', () => {
  test('renders observation/action/reward panels after picking episode', async ({ page }) => {
    await page.goto('/#/decision')

    const select = page.getByRole('combobox')
    await expect(select).toBeVisible()
    const firstId = await select.locator('option').first().getAttribute('value')
    if (firstId) await select.selectOption(firstId)

    await expect(page.getByRole('heading', { name: /觀測|Observation/i })).toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByRole('heading', { name: /動作|Action/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: /獎勵|Reward/i })).toBeVisible()
  })

  test('switching to live mode shows SSE status indicator', async ({ page }) => {
    await page.goto('/#/decision')

    const select = page.getByRole('combobox')
    const firstId = await select.locator('option').first().getAttribute('value')
    if (firstId) await select.selectOption(firstId)

    await page.getByLabel('live').check()
    await expect(page.getByRole('status')).toBeVisible()
    await expect(page).toHaveURL(/mode=live/)
  })

  test('step slider updates URL', async ({ page }) => {
    await page.goto('/#/decision')

    const select = page.getByRole('combobox')
    const firstId = await select.locator('option').first().getAttribute('value')
    if (firstId) await select.selectOption(firstId)

    const slider = page.getByLabel('step')
    await slider.fill('5')
    await expect(page).toHaveURL(/step=5/)
  })
})
