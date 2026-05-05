/**
 * MSW browser worker — 由 main.tsx 在 VITE_USE_MOCK=true 時載入。
 *
 * worker JS 由 `npx msw init public/` 安裝（CI 透過 postinstall script，dev 由開發者一次性執行）。
 */

import { setupWorker } from 'msw/browser'

import { handlers } from './handlers'

export const worker = setupWorker(...handlers)
