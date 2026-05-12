/**
 * E2E — /trajectory：選 episode → K 線渲染 → SMC filter 切換 → URL state 同步。
 */

import { expect, test } from '@playwright/test'

// TODO(task #28): rewrite for sidebar-EpisodeList pattern (009/010 removed
// the page-level `getByRole('combobox')` episode picker).
test.describe.skip('Trajectory page', () => {
  test('renders K-line and SMC filter after picking episode', async ({ page }) => {
    await page.goto('/#/trajectory')
    await expect(page.getByRole('heading', { name: /軌跡|Trajectory/i })).toBeVisible()

    const episodeSelect = page.getByRole('combobox')
    await expect(episodeSelect).toBeVisible()
    const firstId = await episodeSelect.locator('option').first().getAttribute('value')
    if (firstId) await episodeSelect.selectOption(firstId)

    await expect(page.getByRole('figure', { name: /K|SMC/i })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('group')).toBeVisible() // SMCFilter fieldset
  })

  test('toggling SMC filter updates URL search param', async ({ page }) => {
    await page.goto('/#/trajectory')

    const episodeSelect = page.getByRole('combobox')
    const firstId = await episodeSelect.locator('option').first().getAttribute('value')
    if (firstId) await episodeSelect.selectOption(firstId)

    const checkboxes = page.getByRole('checkbox')
    await checkboxes.first().click()

    await expect(page).toHaveURL(/smc=/)
  })
})
