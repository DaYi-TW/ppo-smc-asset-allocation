/**
 * E2E — /overview 路由：載入後可看到圖表與績效摘要，可切換 policy。
 *
 * 依賴 VITE_USE_MOCK=true（MSW browser worker 攔截 /api/v1/*）。
 */

import { expect, test } from '@playwright/test'

test.describe('Overview page', () => {
  test('renders policy picker, weight chart, NAV chart, and summary cards', async ({ page }) => {
    await page.goto('/#/overview')

    await expect(page.getByRole('heading', { name: /戰情總覽|Overview/ })).toBeVisible()

    const select = page.getByRole('combobox')
    await expect(select).toBeVisible()
    await expect(select.locator('option')).toHaveCount(3)

    await expect(page.getByRole('figure', { name: /權重|weight/i })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('figure', { name: /淨值|NAV|drawdown/i })).toBeVisible()
  })

  test('switching policy updates URL search param', async ({ page }) => {
    await page.goto('/#/overview')

    const select = page.getByRole('combobox')
    await select.selectOption('ppo-no-smc-500k')

    await expect(page).toHaveURL(/policy=ppo-no-smc-500k/)
  })
})
