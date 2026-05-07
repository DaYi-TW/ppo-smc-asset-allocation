# PPO + SMC War Room — 前端

戰情室前端（spec 007-react-warroom）— React 18 + TypeScript + Vite。
本目錄為 monorepo subfolder；後端服務見 `specs/005-inference-service/`、`specs/006-spring-gateway/`。

## 範圍

- **檔次 2-local**：單機 docker-compose 論文展示版。
- 不含 JWT/login/audit 頁（FR-013–015 標 `[SCOPE-REDUCED]`，留待檔次 3）。
- 4 個主要頁面：Overview、Trajectory（K 線+SMC）、Decision Panel、Settings。

## 開發

```bash
# 一次設定
nvm use            # 讀 .nvmrc → Node 18.20.x
npm ci             # 安裝鎖定依賴
cp .env.example .env.local

# 日常
npm run dev        # http://localhost:5173
npm run typecheck  # tsc --noEmit
npm run lint       # ESLint
npm run test       # Vitest watch
npm run test:run   # Vitest CI 一次性
npm run test:e2e   # Playwright（需先 npm run dev 或自動 webServer）
npm run build      # 產 dist/
npm run preview    # 預覽 build
```

## Scripts 對照表

| Script             | 用途                                                         |
| ------------------ | ------------------------------------------------------------ |
| `dev`              | Vite dev server (HMR + MSW)                                  |
| `build`            | tsc -b 然後 vite build                                       |
| `preview`          | 預覽 dist 產物                                               |
| `lint` / `lint:fix`| ESLint check / 自動修                                        |
| `format`           | Prettier 一次寫入                                            |
| `typecheck`        | `tsc --noEmit`                                               |
| `test` / `test:run`| Vitest watch / 一次性                                        |
| `test:e2e` / `:ci` | Playwright local / CI（line reporter）                       |
| `gen:api`          | `openapi-typescript` 從 spec 006 contracts 生成 `types.gen.ts`|
| `gen:check`        | 驗證 `types.gen.ts` 已存在                                   |
| `i18n:check`       | `scripts/i18n-check.cjs` — locale 鍵集合一致性               |
| `bundle:check`     | `scripts/bundle-check.cjs` — app shell gzipped ≤ 250 KB      |
| `lighthouse`       | `lhci autorun`（T095，未配置時 placeholder）                 |

## 目錄結構（Phase 1 後逐步擴張）

```
src/
  api/           # T016-T021 fetch/SSE/codegen wrappers
  viewmodels/    # T022-T027 純 TS 介面
  theme/         # T028-T031 token + Tailwind preset
  i18n/          # T032-T034 zh-TW + en
  components/
    common/      # T037-T039 ErrorBoundary、Skeleton、EmptyState
    layout/      # T040-T042 AppShell、TopBar、SideNav
    panels/      # T059, ... policy switcher 等
  routes/        # T061, T076, T083, T091 → /overview /trajectory /decision /settings
  utils/         # T035-T036 format、chart helpers
  test/
    setup.ts     # vitest setup（MSW 啟動）
    fixtures/    # episode/trajectory/policies JSON
    msw/         # handlers + server
tests/
  e2e/           # Playwright spec
```

## 對應 spec / tasks

- spec：`specs/007-react-warroom/spec.md`
- plan：`specs/007-react-warroom/plan.md`
- tasks：`specs/007-react-warroom/tasks.md` (105 tasks，分 7 phase)
- contracts：`specs/007-react-warroom/contracts/`（API DTO、i18n keys、theme tokens）
- data-model：`specs/007-react-warroom/data-model.md`
- research：`specs/007-react-warroom/research.md`
- quickstart：`specs/007-react-warroom/quickstart.md`

## 與後端整合

Phase 2 完成前一律走 MSW mock（`VITE_USE_MOCK=true`）；Phase 3 US1 完成後切真實 backend
時改 `.env.local`：

```env
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8080
```

## 將真實 trajectory.csv 接入 MSW fixture

Feature 003 PPO 訓練完成後，由 `python -m ppo_training.evaluate --save-trajectory ...`
產出 `trajectory.csv`。可用以下指令轉成本前端的 mock fixture：

```bash
node scripts/csv-to-fixture.cjs \
  ../../artifacts/eval/500k_smc_seed42/trajectory.csv \
  src/mocks/fixtures/episode-detail.json \
  ppo-smc-500k v1.0.0
```

注意 CSV 不含 SMC signals / 完整 OHLC / reward 三項分量；converter 會以中性預設值
填補（不影響 NAV / drawdown / 權重視覺化），完整 demo 需另行 join feature 001 的 SMC
特徵與 `data/raw/*.parquet` OHLC。
