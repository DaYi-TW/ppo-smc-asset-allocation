# Implementation Plan: 戰情室前端（React War Room）

**Branch**: `007-react-warroom` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-react-warroom/spec.md`

## Summary

實作論文研究成果展示與互動的「戰情室」前端：以 React 18 + TypeScript（strict）為基礎，
透過 006 Spring Gateway 暴露的 REST + SSE 介面取得歷史 episode、即時推論、SMC 標註與決策
日誌。核心功能包含：權重分配 stacked-area chart、NAV/drawdown 雙軸線圖、K 線圖疊加 SMC
標記（BOS / CHoCh / FVG / OB）、單步決策面板（觀測值 → 動作 → 獎勵元件）。前端必須能在
無後端（mock 模式）下完整 demo 給論文審查者，滿足憲法 Principle II（可解釋性）— 所有
SMC 特徵都必須在 K 線圖上肉眼可驗證。

## Technical Context

**Language/Version**: TypeScript 5.4+（`strict: true`、`noUncheckedIndexedAccess: true`）／
                     Node 18 LTS（CI 與 dev 環境）／React 18.2+
**Primary Dependencies**:
- 框架：React 18.2、Vite 5（dev/build）、React Router 6（hash routing）
- 圖表：`recharts` 2.12（stacked-area / line / bar）、`lightweight-charts` 4.1（TradingView K
  線，輕量、bundle 友善）、`d3-scale` + `d3-array`（自訂尺度與 SMC 標記繪製）
- 資料層：`@tanstack/react-query` 5（caching、retries、SSE pollyfill）、`zod` 3（runtime
  schema 驗證，與 OpenAPI 型別對齊）
- 型別生成：`openapi-typescript` 7（從 006 Gateway openapi.yaml 產生 `src/api/types.gen.ts`）
- 狀態與表單：React Query + URL state；不引入 Redux／Zustand（避免 over-engineering）
- 樣式：Tailwind CSS 3.4（utility-first，搭配 `@tailwindcss/forms`）；CSS variables 暗色主題
- 國際化：`react-i18next` 14（zh-TW 為預設、en 為次要）
- 測試：Vitest 1.5（unit + component）、`@testing-library/react` 14、Playwright 1.43（e2e）、
  MSW 2.2（mock OpenAPI 回應，支援 dev mock 模式 + 測試 fixture）
- 視覺迴歸：Playwright snapshot（`expect(page).toHaveScreenshot()`）

**Storage**: 無持久化儲存；瀏覽器內僅 React Query 快取 + `localStorage` 存使用者偏好（語言、
             主題、預設 policy id）。所有資料來源為 006 Gateway。

**Testing**:
- Unit + component（Vitest + RTL）：純元件、hooks、格式化工具，coverage ≥ 85%
- Contract（MSW 對照 OpenAPI fixture）：每個 API hook 必須有 happy + error 兩個測試
- E2E（Playwright）：4 條 user story 各一條 happy path（FR-021 ≥ 80% 覆蓋）
- 視覺迴歸：權重圖、K 線圖、決策面板各一張快照
- 效能：Lighthouse CI 在 PR 時跑（Performance ≥ 85、Accessibility ≥ 90）

**Target Platform**: 桌機瀏覽器（Chrome 120+、Firefox 120+、Edge 120+）；不支援 IE、不主動
                     最佳化行動版（FR-015 提到響應式為「降級可看」，非主要目標）。

**Project Type**: Web frontend（單一 SPA），位於 monorepo `apps/warroom/`。

**Performance Goals**（對應 spec SC-001 ~ SC-010）：
- 首頁 LCP ≤ 2.5s（Lighthouse 桌機）
- 圖表初次渲染 p95 < 3s（10k 點以內）
- 圖表互動（zoom/pan）≥ 30 fps
- gzipped main JS bundle ≤ 250 KB（不含 lightweight-charts code-split chunk）
- SSE 推論延遲：從 server send 到畫面更新 ≤ 200ms
- TTI ≤ 4s（slow 4G simulation）

**Constraints**:
- 無 backend 時必須能用 MSW mock 完整跑通 4 條 user story（FR-024 demo 模式）
- 必須能在 `npm run build` 後產出純靜態檔案，部署於 nginx 或 S3 + CloudFront
- TypeScript `strict: true`、`exactOptionalPropertyTypes: true`、`noImplicitOverride: true`
- 禁用 `any`（ESLint `@typescript-eslint/no-explicit-any: error`）
- 不引入 jQuery、Lodash 整包（用 `lodash-es` named import 或自寫）
- 不混用樣式方案（只 Tailwind + CSS variables，不 styled-components 也不 CSS-in-JS）
- 資料金額顯示：USD，千分位逗號，小數 2 位（FR-027）；百分比顯示 2 位小數帶 % 符號

**Scale/Scope**：
- 4 個主要頁面（Overview、Trajectory Detail、Single-Step Decision、Settings）
- 約 25 個 React 元件（chart 容器、面板、表格、控制元件）
- 約 12 個 API hooks（每個 Gateway endpoint 一個）
- ~50-70 個實作 task

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I — 可重現性（Reproducibility）NON-NEGOTIABLE
- ✅ 前端不產生研究數據，僅消費 006 Gateway 已寫入後台的 episode／policy 資料；所有顯示
  數值來源 = 後端 byte-identical 結果。
- ✅ 但前端 build 必須可重現：commit `package-lock.json`、CI 使用 `npm ci --frozen`、Node
  版本鎖定在 `.nvmrc`（18.20.x）。
- ✅ MSW mock fixtures（`src/test/fixtures/*.json`）必須是 commit 進 repo 的固定資料快照，
  不得用 `Math.random()` 動態生成。
- 風險：圖表互動有動畫／timing，但這不影響數據正確性，僅影響視覺。

### Principle II — 特徵可解釋性（Explainability）
- ✅ **本 feature 為此原則的主要落實**：FR-009 ~ FR-014 要求 BOS / CHoCh / FVG / OB 在 K
  線圖上以特定圖示／色塊呈現，並提供 hover tooltip 說明判定來源（時間、價格、規則）。
- ✅ 任何新增的 SMC 視覺標記必須有對應的 Storybook（或 Playwright 視覺快照）+ 短說明文字。
- ✅ 決策面板（FR-018 ~ FR-020）必須以**自然語言**敘述「為何選此動作」（policy log-prob、
  最大權重資產、reward 分解的最大正／負貢獻），不接受純數字傾倒。

### Principle III — 風險優先獎勵（Risk-First Reward）NON-NEGOTIABLE
- N/A：前端不定義 reward；但 FR-019 規定「決策面板必須顯示 reward 三大元件（return、
  drawdown penalty、cost penalty）的當期數值與累積值」，使用者得以肉眼驗證 reward 設計
  是否風險優先。本 feature **被動實踐**此原則。

### Principle IV — 微服務解耦（Service Decoupling）
- ✅ React 戰情室是三層架構的最終層；本 feature 嚴守此原則。
- ✅ 唯一資料介面 = 006 Gateway HTTP/SSE；不直接打 005 Inference Service、不直接讀 002
  資料快照、不直接讀 003 environment 內部狀態。
- ✅ API client 從 006 OpenAPI yaml 自動生成型別；breaking change 在 CI 階段就會編譯失敗。
- ✅ Mock 模式（MSW）也是對 OpenAPI 的 mock，不繞過契約。

### Principle V — 規格先行（Spec-First）NON-NEGOTIABLE
- ✅ spec.md 已先於本 plan 完成 review（179 行、4 user stories、31 FRs、10 SCs）。
- ✅ 本 plan 不擴張範圍（不加聊天室、不加 user 管理 — 那是新 feature）。
- ✅ 跨層介面變動（如 006 OpenAPI 修改）必須先在 006 spec 改、本 feature 透過重新跑 codegen
  接收。

**Initial Constitution Check**: PASS（無偏離條目，無待補例外）

## Project Structure

### Documentation (this feature)

```
specs/007-react-warroom/
├── plan.md              # 本文件
├── research.md          # Phase 0：技術選型決策（Recharts vs Plotly、KLine 套件比較等）
├── data-model.md        # Phase 1：前端 TypeScript view model 與 API 對應
├── contracts/
│   ├── ui-routes.md     # 路由表與 layout 契約
│   ├── api-mapping.md   # 從 006 OpenAPI 到前端 hook 名稱的對應
│   ├── theme-tokens.md  # 設計 token（顏色、間距、字型）
│   └── i18n-keys.md     # i18n key naming convention 與 zh-TW/en 對照表
├── quickstart.md        # Phase 1：開發者快速上手（npm install → npm run dev → mock 模式）
└── tasks.md             # Phase 2：實作 tasks（由 /speckit.tasks 產生）
```

### Source Code (repository root)

```
apps/warroom/                          # Vite + React 18 + TypeScript 專案
├── package.json
├── package-lock.json
├── tsconfig.json
├── tsconfig.node.json                 # Vite config 的 TS 設定
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.cjs
├── playwright.config.ts
├── vitest.config.ts
├── index.html
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx                       # entry point
│   ├── App.tsx                        # router + providers
│   ├── routes/
│   │   ├── overview.tsx               # P1 stacked-area + NAV/drawdown
│   │   ├── trajectory.tsx             # P2 K 線 + SMC 疊加
│   │   ├── decision.tsx               # P3 單步決策面板
│   │   └── settings.tsx               # 主題、語言、預設 policy
│   ├── components/
│   │   ├── charts/
│   │   │   ├── WeightStackedArea.tsx
│   │   │   ├── NavDrawdownChart.tsx
│   │   │   ├── KLineWithSMC.tsx       # lightweight-charts wrapper + SMC overlay
│   │   │   └── RewardBreakdown.tsx
│   │   ├── panels/
│   │   │   ├── PolicyPicker.tsx
│   │   │   ├── EpisodeMeta.tsx
│   │   │   ├── ActionVector.tsx
│   │   │   └── ObservationTable.tsx
│   │   ├── layout/
│   │   │   ├── AppShell.tsx
│   │   │   ├── TopBar.tsx
│   │   │   └── SideNav.tsx
│   │   └── common/
│   │       ├── ErrorBoundary.tsx
│   │       ├── LoadingSkeleton.tsx
│   │       └── EmptyState.tsx
│   ├── hooks/
│   │   ├── useEpisodeList.ts
│   │   ├── useEpisodeDetail.ts
│   │   ├── useEpisodeStream.ts        # SSE
│   │   ├── useInfer.ts
│   │   ├── usePolicies.ts
│   │   └── useTheme.ts
│   ├── api/
│   │   ├── client.ts                  # fetch wrapper + auth header injection
│   │   ├── types.gen.ts               # 由 openapi-typescript 從 006 yaml 產生（不手改）
│   │   ├── envelopes.ts               # API → ViewModel 轉換（CamelCase 已由 Gateway 處理）
│   │   └── sse.ts                     # SSE 客戶端
│   ├── viewmodels/
│   │   ├── episode.ts                 # EpisodeViewModel
│   │   ├── trajectory.ts              # TrajectoryFrame
│   │   ├── smc.ts                     # SMCMarker
│   │   └── reward.ts                  # RewardBreakdown
│   ├── i18n/
│   │   ├── index.ts                   # i18next 初始化
│   │   ├── zh-TW.json
│   │   └── en.json
│   ├── theme/
│   │   ├── tokens.ts                  # 設計 token 定數
│   │   └── tailwind-preset.ts
│   ├── utils/
│   │   ├── format.ts                  # 數字、百分比、日期格式化
│   │   └── chart-helpers.ts
│   ├── test/
│   │   ├── setup.ts                   # vitest setup（jsdom、MSW server）
│   │   ├── fixtures/
│   │   │   ├── episode-list.json
│   │   │   ├── episode-detail.json
│   │   │   └── policies.json
│   │   └── mocks/
│   │       ├── handlers.ts            # MSW request handlers
│   │       └── browser.ts             # MSW browser worker（dev mock 模式）
│   └── env.d.ts
├── tests/
│   ├── unit/                          # Vitest unit
│   │   ├── format.test.ts
│   │   └── envelopes.test.ts
│   ├── component/                     # Vitest + RTL
│   │   ├── WeightStackedArea.test.tsx
│   │   ├── NavDrawdownChart.test.tsx
│   │   └── RewardBreakdown.test.tsx
│   └── e2e/                           # Playwright
│       ├── overview.spec.ts
│       ├── trajectory.spec.ts
│       ├── decision.spec.ts
│       └── visual/                    # 視覺快照
│           └── snapshots.spec.ts
└── README.md
```

**Structure Decision**: Single SPA under `apps/warroom/`，與 006 `services/gateway/`、005
`services/inference/`、004 `src/training/`、003 `src/envs/` 平行；monorepo 不引入 npm
workspaces（前端只一個 app，避免過度設計）。所有 API 型別由 codegen 從 006 OpenAPI yaml
取得，避免手動維護導致漂移。

## Complexity Tracking
*無偏離項目，本節保留供後續修訂使用。*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|-----------|---------------------------------------|
| (none)    | (none)    | (none)                                |

---

## Phase 0 Output

請見 [research.md](./research.md) — 12 個技術選型決策（圖表庫、狀態管理、i18n、mock 策略、
codegen 工具、視覺迴歸方案等）。

## Phase 1 Output

- [data-model.md](./data-model.md)：前端 TypeScript view model + 與 006 API DTO 的轉換契約。
- [contracts/ui-routes.md](./contracts/ui-routes.md)：路由表、layout 結構、URL state 規約。
- [contracts/api-mapping.md](./contracts/api-mapping.md)：006 OpenAPI 端點 → React Query
  hook 對應表。
- [contracts/theme-tokens.md](./contracts/theme-tokens.md)：設計 token、暗色／亮色主題切換。
- [contracts/i18n-keys.md](./contracts/i18n-keys.md)：i18n key 命名規約與 zh-TW／en 對照。
- [quickstart.md](./quickstart.md)：開發者 5 分鐘上手（含 mock 模式 demo）。

## Phase 2 — Tasks

由 `/speckit.tasks` 產生 [tasks.md](./tasks.md)。

---

**Post-Design Constitution Check**: PASS（Phase 1 完成後無新偏離）

**Plan complete — ready for `/speckit.tasks`**
