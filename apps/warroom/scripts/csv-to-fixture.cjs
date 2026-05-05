#!/usr/bin/env node
/**
 * trajectory.csv → MSW fixture JSON converter.
 *
 * 將 `python -m ppo_training.evaluate --save-trajectory` 產出的 CSV 轉為
 * `apps/warroom/src/mocks/fixtures/episode-detail.json` 可吃的 trajectory frames。
 *
 * CSV 欄位（src/ppo_training/evaluate.py:243）：
 *   date, nav, log_return,
 *   w_NVDA, w_AMD, w_TSM, w_MU, w_GLD, w_TLT, w_CASH,
 *   close_NVDA, close_AMD, close_TSM, close_MU, close_GLD, close_TLT
 *
 * 注意：CSV 不含 SMC signals / OHLC（除 close）/ reward decomposition。
 * 本 converter 對缺少欄位填預設值（NaN/0/false），下游視覺化會優雅退化。
 * 若要完整 SMC + OHLC，需要分別從 feature 001 (smc_features) 與
 * data/raw/*.parquet 讀取後 join。本檔次 2-local 範圍內，現有 hand-crafted
 * fixture 已足以 demo；此 script 為 feature 003+ 完整 trajectory 接入時備用。
 *
 * 用法：
 *   node scripts/csv-to-fixture.cjs <input-csv> <output-json> [policyId] [policyVersion]
 *
 * 例：
 *   node scripts/csv-to-fixture.cjs \
 *     ../../artifacts/eval/500k_smc_seed42/trajectory.csv \
 *     src/mocks/fixtures/episode-detail.json \
 *     ppo-smc-500k v1.0.0
 */

const fs = require('fs')
const path = require('path')

const ASSETS = ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT', 'CASH']
const RISK_ON = ['NVDA', 'AMD', 'TSM', 'MU']
const RISK_OFF = ['GLD', 'TLT']

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0)
  if (lines.length < 2) throw new Error('CSV has no data rows')
  const header = lines[0].split(',').map((s) => s.trim())
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(',').map((s) => s.trim())
    const row = {}
    header.forEach((h, i) => {
      row[h] = cells[i]
    })
    return row
  })
  return { header, rows }
}

function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function buildFrame(row, step, prevPeakNav, initialNav) {
  const date = row['date']
  const nav = num(row['nav']) * initialNav
  const peakNav = Math.max(prevPeakNav, nav)
  const drawdownPct = peakNav > 0 ? (nav - peakNav) / peakNav : 0
  const logReturn = num(row['log_return'])

  const perAsset = {}
  for (const a of ASSETS) perAsset[a] = num(row[`w_${a}`])

  const riskOn = RISK_ON.reduce((acc, a) => acc + perAsset[a], 0)
  const riskOff = RISK_OFF.reduce((acc, a) => acc + perAsset[a], 0)
  const cash = perAsset['CASH']

  const close = num(row['close_NVDA']) || 0

  // OHLC 不在 CSV — 使用 close 當代理（前後比較產生粗略 high/low）。
  const open = close
  const high = close
  const low = close

  // Reward decomposition not in CSV — 用 log_return 當作 returnComponent，
  // drawdown/cost penalty 設 0（demo 視覺化會顯示為 0 bar）。
  const reward = {
    total: logReturn,
    returnComponent: logReturn,
    drawdownPenalty: 0,
    costPenalty: 0,
  }

  // SMC signals not in CSV — 預設 neutral（讓 K-line 不顯示標記）。
  // 注意：JSON 不支援 NaN（會序列化為 null），下游 DTO 要求 number，故用 0。
  const smcSignals = {
    bos: 0,
    choch: 0,
    fvgDistancePct: 0,
    obTouching: false,
    obDistanceRatio: 0,
  }

  const action = {
    raw: ASSETS.map((a) => perAsset[a]),
    normalized: ASSETS.map((a) => perAsset[a]),
    logProb: 0,
    entropy: 0,
  }

  return {
    timestamp: date,
    step,
    weights: { riskOn, riskOff, cash, perAsset },
    nav,
    drawdownPct,
    reward,
    smcSignals,
    ohlcv: { open, high, low, close, volume: 0 },
    action,
    _peakNav: peakNav, // internal — stripped before emit
  }
}

function computeMetrics(frames) {
  if (frames.length === 0) return { totalReturn: 0, maxDrawdown: 0, sharpeRatio: 0 }
  const initialNav = frames[0].nav
  const finalNav = frames[frames.length - 1].nav
  const totalReturn = (finalNav - initialNav) / initialNav

  const maxDrawdown = frames.reduce((m, f) => Math.min(m, f.drawdownPct), 0)

  const logReturns = frames.slice(1).map((f, i) => {
    const prev = frames[i].nav
    return prev > 0 ? Math.log(f.nav / prev) : 0
  })
  const mean = logReturns.reduce((a, b) => a + b, 0) / Math.max(1, logReturns.length)
  const variance =
    logReturns.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, logReturns.length)
  const std = Math.sqrt(variance)
  const sharpeRatio = std > 0 ? (mean / std) * Math.sqrt(252) : 0

  return { totalReturn, maxDrawdown, sharpeRatio }
}

function buildRewardBreakdown(frames) {
  let cumTotal = 0
  let cumReturn = 0
  let cumDrawdown = 0
  let cumCost = 0
  const cumulative = []
  const byStep = []
  for (const f of frames) {
    cumTotal += f.reward.total
    cumReturn += f.reward.returnComponent
    cumDrawdown += f.reward.drawdownPenalty
    cumCost += f.reward.costPenalty
    cumulative.push({
      step: f.step,
      cumulativeTotal: cumTotal,
      cumulativeReturn: cumReturn,
      cumulativeDrawdownPenalty: cumDrawdown,
      cumulativeCostPenalty: cumCost,
    })
    byStep.push({
      total: f.reward.total,
      returnComponent: f.reward.returnComponent,
      drawdownPenalty: f.reward.drawdownPenalty,
      costPenalty: f.reward.costPenalty,
    })
  }
  return { cumulative, byStep }
}

function main() {
  const [, , inputCsv, outputJson, policyId, policyVersion] = process.argv
  if (!inputCsv || !outputJson) {
    console.error(
      'Usage: node scripts/csv-to-fixture.cjs <input-csv> <output-json> [policyId] [policyVersion]',
    )
    process.exit(1)
  }
  if (!fs.existsSync(inputCsv)) {
    console.error(`[csv-to-fixture] Input CSV not found: ${inputCsv}`)
    process.exit(1)
  }

  const csvText = fs.readFileSync(inputCsv, 'utf8')
  const { rows } = parseCsv(csvText)

  const initialNav = 100_000
  let peakNav = 0
  const frames = rows.map((row, i) => {
    const f = buildFrame(row, i, peakNav, initialNav)
    peakNav = f._peakNav
    delete f._peakNav
    return f
  })

  const metrics = computeMetrics(frames)
  const rewardBreakdown = buildRewardBreakdown(frames)

  const startDate = frames[0]?.timestamp ?? ''
  const endDate = frames[frames.length - 1]?.timestamp ?? ''

  const detail = {
    episodeId: `ep-${path.basename(inputCsv, '.csv')}`,
    policyId: policyId ?? 'ppo-smc-500k',
    policyVersion: policyVersion ?? 'v1.0.0',
    startDate,
    endDate,
    totalReturn: metrics.totalReturn,
    maxDrawdown: metrics.maxDrawdown,
    sharpeRatio: metrics.sharpeRatio,
    totalSteps: frames.length,
    status: 'completed',
    createdAt: new Date().toISOString(),
    config: {
      initialNav,
      symbols: ASSETS,
      rebalanceFrequency: 'daily',
      transactionCostBps: 5,
      slippageBps: 2,
      riskFreeRate: 0.045,
    },
    trajectoryInline: frames,
    rewardBreakdown,
  }

  const outDir = path.dirname(outputJson)
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })
  fs.writeFileSync(outputJson, JSON.stringify(detail, null, 2) + '\n', 'utf8')
  console.log(
    `[csv-to-fixture] Wrote ${frames.length} frames → ${outputJson} (totalReturn=${(
      metrics.totalReturn * 100
    ).toFixed(2)}%, MDD=${(metrics.maxDrawdown * 100).toFixed(2)}%, Sharpe=${metrics.sharpeRatio.toFixed(2)})`,
  )
}

main()
