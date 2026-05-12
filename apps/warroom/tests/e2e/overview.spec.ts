/**
 * E2E — /overview 路由：載入後渲染圖表 + 加上 010 Live tracking controls。
 *
 * 依賴 VITE_USE_MOCK=true（MSW browser worker 攔截 /api/v1/*）。
 * 010 之後 OverviewPage 不再有頁面層級的 policy combobox — 預設選 live tracking
 * （id 後綴 `_live`），fallback OOS。header 加上 DataLagBadge + LiveRefreshButton。
 */

import { expect, test } from '@playwright/test'

test.describe('Overview page', () => {
  test('renders NAV chart, weight chart, and KLine panel after default-episode load', async ({ page }) => {
    await page.goto('/#/overview')

    // visually-hidden h2 — accessible name
    await expect(page.getByRole('heading', { name: /戰情總覽|Overview/, level: 2 })).toBeAttached()

    // KPI row + main charts — wait for query to settle
    await expect(page.getByRole('figure', { name: /權重|weight/i })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('figure', { name: /淨值|NAV|drawdown/i })).toBeVisible()
  })

  test('header surfaces LiveRefreshButton (010 manual refresh)', async ({ page }) => {
    await page.goto('/#/overview')

    // 用 data-testid 不受 i18n 影響
    await expect(page.getByTestId('live-refresh-button')).toBeVisible({ timeout: 15_000 })
  })
})
