#!/usr/bin/env node
/**
 * i18n key completeness check — 確保所有 supported locales 的 JSON 鍵集合一致。
 *
 * 用法：node scripts/i18n-check.cjs
 * 失敗條件：locales 之間鍵集合不一致（任何一方缺鍵）。
 */
const fs = require('fs')
const path = require('path')

const LOCALES_DIR = path.join(__dirname, '..', 'src', 'i18n', 'locales')

function flattenKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...flattenKeys(v, full))
    } else {
      keys.push(full)
    }
  }
  return keys
}

function loadLocale(file) {
  const content = fs.readFileSync(path.join(LOCALES_DIR, file), 'utf8')
  return JSON.parse(content)
}

function main() {
  const files = fs.readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json'))
  if (files.length === 0) {
    console.error('[i18n-check] No locale files found.')
    process.exit(1)
  }

  const keysByLocale = new Map()
  for (const f of files) {
    keysByLocale.set(f, new Set(flattenKeys(loadLocale(f))))
  }

  const allKeys = new Set()
  for (const set of keysByLocale.values()) {
    for (const k of set) allKeys.add(k)
  }

  let errors = 0
  for (const [file, set] of keysByLocale.entries()) {
    const missing = [...allKeys].filter((k) => !set.has(k))
    if (missing.length > 0) {
      console.error(`[i18n-check] ${file} missing ${missing.length} keys:`)
      for (const k of missing) console.error(`  - ${k}`)
      errors += missing.length
    }
  }

  if (errors > 0) {
    console.error(`[i18n-check] FAILED: ${errors} missing key(s).`)
    process.exit(1)
  }
  console.log(`[i18n-check] OK — ${allKeys.size} keys × ${files.length} locales.`)
}

main()
