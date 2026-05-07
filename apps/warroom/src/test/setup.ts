/**
 * Vitest setup — jsdom 環境補強、testing-library jest-dom matchers、MSW node server。
 *
 * MSW node server 用於單元/integration test 攔截 API；
 * E2E（Playwright）走真實瀏覽器，使用 mocks/browser.ts 的 service worker。
 */

import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from '@/mocks/server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// jsdom 不實作 matchMedia；提供 stub 讓 applyTheme/watchSystemTheme 不爆。
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}

// jsdom 不實作 ResizeObserver；Recharts ResponsiveContainer 需要它。
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub implements ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  ;(globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver
}
