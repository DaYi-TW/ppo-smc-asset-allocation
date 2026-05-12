/**
 * E2E — /trajectory：自動選 first episode → K 線渲染 → SMC filter 切換 → URL state 同步。
 *
 * 009/010 後 EpisodePicker 還在 TrajectoryPage 的 <header>，但 AppShell footer
 * 也有 locale/theme select 會撞 page-level `getByRole('combobox')`。改成用
 * `main` scope 過濾，並用 EpisodePicker 的 label「選擇 Episode」精準定位。
 */

import { expect, test } from '@playwright/test'

test.describe('Trajectory page', () => {
  test('renders K-line after default-episode auto-fill', async ({ page }) => {
    await page.goto('/#/trajectory')

    await expect(
      page.getByRole('heading', { name: /軌跡|Trajectory/i, level: 2 }),
    ).toBeVisible()

    // EpisodePicker label 是「選擇 Episode」（zh-TW 預設）或「Choose Episode」
    const episodePicker = page.getByLabel(/選擇 Episode|Choose Episode/i)
    await expect(episodePicker).toBeVisible({ timeout: 10_000 })

    // 自動選首筆 → URL 帶 ?episode=
    await expect(page).toHaveURL(/episode=/, { timeout: 10_000 })

    // K 線 figure（accessible name = trajectory.kline.title）
    const main = page.getByRole('main')
    await expect(main.getByRole('heading', { name: /K 線|K-line/i })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('toggling SMC filter updates URL search param', async ({ page }) => {
    await page.goto('/#/trajectory')

    // 等 episode 自動填入
    await expect(page).toHaveURL(/episode=/, { timeout: 10_000 })

    // SMCFilter 是 fieldset，內含 checkbox。scope 到 main 避免 AppShell 干擾
    const main = page.getByRole('main')
    const checkboxes = main.getByRole('checkbox')
    await expect(checkboxes.first()).toBeVisible({ timeout: 10_000 })
    await checkboxes.first().click()

    await expect(page).toHaveURL(/smc=/)
  })
})
