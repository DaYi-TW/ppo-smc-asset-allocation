/**
 * E2E — /settings：切語言 → UI 翻譯；切主題 → <html> 加 .dark；reload 後保留。
 */

import { expect, test } from '@playwright/test'

test.describe('Settings page', () => {
  test('language change updates UI without reload', async ({ page }) => {
    await page.goto('/#/settings')

    const langSelect = page.getByLabel(/介面語言|Language/i)
    await langSelect.selectOption('en')

    await expect(page.getByRole('heading', { name: /Settings/i })).toBeVisible()
  })

  test('theme change toggles <html>.dark and persists across reload', async ({ page }) => {
    await page.goto('/#/settings')

    const themeSelect = page.getByLabel(/主題|Theme/i)
    await themeSelect.selectOption('dark')

    await expect(page.locator('html')).toHaveClass(/dark/)

    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
  })
})
