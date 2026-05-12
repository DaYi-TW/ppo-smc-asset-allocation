/**
 * E2E — /settings：切語言 → UI 翻譯；切主題 → <html> 加 .dark；reload 後保留。
 *
 * 007 後 AppShell TopBar 跟 SettingsPage 各有獨立 useUserPrefs state（同 tab 不互通，
 * 只跨 tab 透過 storage event 同步）。語言切換的「即時生效」靠 App.tsx watch
 * preferences.language → i18n.changeLanguage —— 必須改 TopBar 的 select（App-level
 * state）才會觸發 i18n.changeLanguage。改 SettingsPage 內 select 只改自身狀態。
 *
 * 主題切換在 SettingsPage 內可生效，因為 useTheme 直接寫 <html>.classList，
 * 不依賴 App-level state propagation。
 */

import { expect, test } from '@playwright/test'

test.describe('Settings page', () => {
  test('language change updates UI without reload', async ({ page }) => {
    await page.goto('/#/settings')

    // TopBar (banner) locale select — App.tsx 監聽這個 state 觸發 i18n.changeLanguage
    const banner = page.getByRole('banner')
    const langSelect = banner.getByLabel(/介面語言|Language/i)
    await langSelect.selectOption('en')

    // English heading 出現（SettingsPage 用 t('settings.title') = "Settings"）
    await expect(
      page.getByRole('heading', { name: /Settings/i, level: 2 }),
    ).toBeVisible()
  })

  test('theme change toggles <html>.dark and persists across reload', async ({ page }) => {
    await page.goto('/#/settings')

    const main = page.getByRole('main')
    const themeSelect = main.getByLabel(/主題|Theme/i)
    await themeSelect.selectOption('dark')

    await expect(page.locator('html')).toHaveClass(/dark/)

    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
  })
})
