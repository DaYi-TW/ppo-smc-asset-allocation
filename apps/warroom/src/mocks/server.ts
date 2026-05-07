/**
 * MSW node server — 用於 vitest 單元/integration 測試。
 */

import { setupServer } from 'msw/node'

import { handlers } from './handlers'

export const server = setupServer(...handlers)
