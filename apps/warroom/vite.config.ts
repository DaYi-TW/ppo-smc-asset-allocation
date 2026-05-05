/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    manifest: true,
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks: {
          recharts: ['recharts'],
          lwc: ['lightweight-charts'],
          d3: ['d3-array', 'd3-scale'],
          query: ['@tanstack/react-query'],
          i18n: ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    exclude: ['node_modules', 'dist', 'tests/e2e/**'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      thresholds: {
        lines: 70,
        statements: 70,
        functions: 70,
        branches: 60,
      },
    },
  },
})
