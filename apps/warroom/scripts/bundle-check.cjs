#!/usr/bin/env node
/**
 * Bundle size check — 確保 dist/assets/index-*.js（app shell）gzipped ≤ 250 KB。
 *
 * 用法：先 vite build，再 node scripts/bundle-check.cjs
 * 對應 spec SC-003 main bundle ≤ 250 KB。
 */
const fs = require('fs')
const path = require('path')
const zlib = require('zlib')

const DIST_DIR = path.join(__dirname, '..', 'dist', 'assets')
const LIMIT_KB = 250

function main() {
  if (!fs.existsSync(DIST_DIR)) {
    console.error('[bundle-check] dist/assets not found — run `vite build` first.')
    process.exit(1)
  }
  const files = fs.readdirSync(DIST_DIR).filter((f) => /^index-.*\.js$/.test(f))
  if (files.length === 0) {
    console.error('[bundle-check] No app shell index-*.js found in dist/assets.')
    process.exit(1)
  }

  let total = 0
  for (const f of files) {
    const buf = fs.readFileSync(path.join(DIST_DIR, f))
    const gz = zlib.gzipSync(buf)
    const kb = gz.length / 1024
    total += kb
    console.log(`[bundle-check] ${f}: ${kb.toFixed(2)} KB gzipped`)
  }
  console.log(`[bundle-check] App shell total: ${total.toFixed(2)} KB / limit ${LIMIT_KB} KB`)
  if (total > LIMIT_KB) {
    console.error(`[bundle-check] FAILED — exceeds ${LIMIT_KB} KB by ${(total - LIMIT_KB).toFixed(2)} KB`)
    process.exit(1)
  }
  console.log('[bundle-check] OK')
}

main()
