# Phase 0 Research: 戰情室前端技術選型

**Feature**: 007-react-warroom
**Date**: 2026-04-29

本文件彙整 12 個關鍵技術決策。每個決策含 Decision、Rationale、Alternatives Considered。

---

## R1：圖表庫主軸 — Recharts vs Plotly vs Victory vs Nivo

**Decision**：以 **Recharts 2.12** 作為主要 SVG 圖表庫（用於 stacked-area、line、bar），
搭配 **lightweight-charts 4.1** 處理 K 線圖（見 R2）。

**Rationale**：
- Recharts 以 React 元件方式宣告（`<AreaChart><Area /><XAxis />`），與本專案 React 18 慣
  例契合，學習成本低。
- bundle 體積：Recharts gzipped ≈ 95 KB（tree-shaken），Plotly ≈ 1.2 MB（爆掉 250 KB
  budget），Victory ≈ 110 KB，Nivo ≈ 130 KB。
- Recharts 支援我們需要的所有圖型（stacked-area、雙軸 line、bar、scatter）。
- TypeScript 型別完整，社群活躍（每月發版）。

**Alternatives Considered**：
- **Plotly.js**：功能最強但 bundle 太大；只在科研 notebook 場景值得。拒絕。
- **Victory**：API 設計優雅但效能較差，10k 點以上會明顯卡頓。拒絕。
- **Nivo**：視覺漂亮但客製化空間少；K 線圖不支援。拒絕。
- **Pure D3**：自由度最高但開發成本高 3-5 倍，本專案是論文 demo 不是長期產品。
  保留為 SMC overlay 的補強（見 R2）。

---

## R2：K 線圖元件 — TradingView lightweight-charts vs ApexCharts vs 自寫

**Decision**：採用 **lightweight-charts 4.1**，並以 D3 在其 canvas 上層繪製 SMC 標記
（BOS／CHoCh／FVG／OB）。

**Rationale**：
- TradingView 出品，業界 K 線圖事實標準；金融分析使用者熟悉操作。
- 使用 canvas 渲染，10k+ K 棒效能優異（≥ 30 fps zoom/pan）。
- bundle gzipped ≈ 45 KB，遠優於 ApexCharts（~120 KB）。
- 提供 plugin API（`createCustomSeries`），可疊加自訂標記層。
- MIT license。

**Alternatives Considered**：
- **ApexCharts**：bundle 較大、效能在 10k 點時退化。拒絕。
- **react-financial-charts**：D3 包裝、effort 重、社群不活躍。拒絕。
- **自寫 D3 + canvas**：完整自由度但 3-4 週開發，論文時程不容許。拒絕。

**SMC overlay 方案**：使用 lightweight-charts 提供的 `setMarkers()`（BOS／CHoCh 用箭頭與
標籤）+ 一個獨立透明 `<canvas>` 蓋在上層用 D3 繪製 FVG 矩形與 OB 區塊（透過
`chart.timeScale().timeToCoordinate()` 取得 X 座標）。

---

## R3：狀態管理 — React Query 單獨 vs +Redux vs +Zustand vs Jotai

**Decision**：**只用 React Query 5（@tanstack/react-query）+ URL state**，不引入全域狀態
管理庫。

**Rationale**：
- 戰情室幾乎所有狀態都是 server state（episode list、trajectory、policy metadata），React
  Query 為其量身打造（cache、refetch、stale-while-revalidate、SSE）。
- UI state（選中的 episode id、目前的時間範圍、放大區段）放 URL hash params，方便分享連結。
- 使用者偏好（語言、主題）放 `localStorage` + 一個輕量的 `useUserPrefs` hook。
- 引入 Redux／Zustand 是 over-engineering，會增加新進開發者的心智負擔。

**Alternatives Considered**：
- **Redux Toolkit**：適合大型 SPA，本專案頁面少不必要。拒絕。
- **Zustand**：輕量但仍是 server state 重複造輪。拒絕。
- **Jotai／Recoil**：atomic state 模型不符本專案使用情境。拒絕。

---

## R4：API 型別生成 — openapi-typescript vs orval vs hey-api/openapi-ts

**Decision**：**openapi-typescript 7**（drizzle/openapi-typescript），只生成 type，不生成
fetch client；fetch client 自寫 thin wrapper（`src/api/client.ts`）。

**Rationale**：
- 我們需要的是「型別契約」而非完整 SDK。openapi-typescript 產出的 `paths`、`components`
  type 已足夠搭配 React Query 的 `useQuery<TData>(key, fetcher)` 使用。
- 自寫 client 控制權高：可加入 auth header、Idempotency-Key、retry 邏輯、SSE 切換。
- Orval、hey-api 會生成大量我們用不到的 hooks／schema 程式碼，膨脹 bundle。
- 可在 CI 加入 `npm run gen:api -- --check` 確保生成檔未被手改（drift detection）。

**Alternatives Considered**：
- **Orval**：自動生成 React Query hooks，但 hook 命名與本專案 convention 不符。拒絕。
- **hey-api/openapi-ts**：較新、文件較少、TypeScript output 較粗。拒絕。

---

## R5：Mock 策略 — MSW vs json-server vs Mirage.js

**Decision**：**MSW 2.2（service worker + Node integration）**，fixture 為靜態 JSON。

**Rationale**：
- 同時支援瀏覽器（dev 與 e2e mock 模式）與 Node（vitest 測試），一份 handler 兩用。
- 不需另外起一個 server process（json-server 要佔 port、mirage 不支援 Node）。
- 與 React Query／fetch 透明整合，不需改 production 程式碼。
- 支援 SSE mock（透過 `transformer.text` 流式回應）。
- v2 已穩定（2024 Q1 release）。

**Alternatives Considered**：
- **json-server**：簡單但無法 mock SSE、無法在 vitest 用。拒絕。
- **Mirage.js**：API 古怪、社群衰退中。拒絕。

**Demo 模式啟動方式**：在 `.env.development` 設 `VITE_USE_MOCK=true`，`main.tsx` 啟動時
若旗標為真則 `await worker.start()`。Production build 不打包 MSW handler。

---

## R6：i18n 框架 — react-i18next vs LinguiJS vs FormatJS

**Decision**：**react-i18next 14** + JSON 資源檔；預設 zh-TW、次要 en。

**Rationale**：
- 戰情室預設給中文論文審查者使用，但需保留英文版以便國際投稿展示。
- react-i18next API 直觀（`useTranslation()` hook），文件中文化好。
- 支援 nested key、interpolation、pluralization（雖然本專案少用 plural）。
- bundle gzipped ≈ 18 KB（含 i18next core + react binding）。

**Alternatives Considered**：
- **LinguiJS**：訊息內嵌 JSX 強大但需 babel macro，build 鏈複雜化。拒絕。
- **FormatJS／react-intl**：標準正宗但 boilerplate 多、icu message 對中文 contributor 不友善。拒絕。

**Key naming convention**（contract 詳述於 `contracts/i18n-keys.md`）：
`<page>.<component>.<element>`，例：`overview.weightChart.legend.riskOn`。

---

## R7：CSS 方案 — Tailwind vs CSS Modules vs styled-components

**Decision**：**Tailwind CSS 3.4** + 必要時的 CSS variables（暗色／亮色主題切換）。

**Rationale**：
- utility-first 寫法快速；論文 demo 強調快出原型。
- 暗色主題用 `class="dark"` 切換 + `dark:bg-gray-900` 寫法，無需額外架構。
- bundle 經 PurgeCSS 後 gzipped ≈ 12 KB（只保留實際用到的 class）。
- 與 Recharts、lightweight-charts 共存無衝突（後者用 inline style）。

**Alternatives Considered**：
- **CSS Modules**：寫起來囉嗦、不易快速調整。拒絕。
- **styled-components／Emotion**：runtime overhead、bundle 較大、SSR 配置複雜。拒絕。
- **Vanilla Extract**：build-time 但 ergonomics 不及 Tailwind。拒絕。

---

## R8：表單／表格 — 自寫 vs TanStack Table vs react-hook-form

**Decision**：表格用 **TanStack Table 8**（headless），表單因 input 數量極少（settings 頁
3 個欄位）採**原生 controlled component**，不引入 react-hook-form。

**Rationale**：
- 表格場景：episode list、trajectory frame list、observation table — TanStack Table 的
  排序／過濾／分頁 headless API 與 Tailwind 渲染分離，符合本專案風格。
- 表單場景太小，react-hook-form（gzipped ~11 KB）不划算。

**Alternatives Considered**：
- **AG Grid**：功能最完整但 license 商用版限制 + bundle 巨大。拒絕。
- **Material UI Table**：耦合 MUI 設計系統。拒絕。

---

## R9：Routing — React Router vs TanStack Router vs Wouter

**Decision**：**React Router 6.22**（hash routing 模式 — `createHashRouter`）。

**Rationale**：
- hash routing 部署於靜態 host（S3、nginx）無需後端 rewrite 規則，符合純前端 SPA 場景。
- React Router 6 的 data router API（loaders）可與 React Query prefetch 整合。
- 社群最大、文件最完整，新進開發者熟悉度高。

**Alternatives Considered**：
- **TanStack Router**：型別安全強但 API 仍在演化、文件較少。拒絕。
- **Wouter**：bundle 小但功能不足（無 nested routes data flow）。拒絕。

---

## R10：測試框架 — Vitest vs Jest，Playwright vs Cypress

**Decision**：unit/component 用 **Vitest 1.5 + Testing Library**；e2e 用 **Playwright 1.43**。

**Rationale**：
- Vitest 與 Vite 同源，不需另外配置 babel／transformer，TypeScript 原生支援快。
- Playwright 比 Cypress：
  - 多瀏覽器並行（chromium/firefox/webkit）
  - 視覺快照 native 支援（`toHaveScreenshot()`），Cypress 需 plugin
  - SSE / WebSocket 測試友好
  - bundle 較小、執行較快

**Alternatives Considered**：
- **Jest**：與 Vite 雙 build chain 麻煩、ESM 支援差。拒絕。
- **Cypress**：開發 ergonomics 好但多 tab／視覺快照支援弱。拒絕。

---

## R11：視覺迴歸 — Playwright snapshot vs Chromatic vs Percy

**Decision**：**Playwright 內建 `toHaveScreenshot()`** + 在 GitHub Actions 上跑（artifact
存放快照）；不引入 Chromatic／Percy。

**Rationale**：
- 論文 demo 規模小（5-8 張快照），不需專業視覺平台。
- Chromatic／Percy 商業服務，免費 quota 對開源論文 repo 仍可能不夠。
- Playwright snapshot 會把 baseline PNG commit 進 repo，與「資料快照進 repo」（憲法
  Principle I）哲學一致。

**Alternatives Considered**：
- **Chromatic**：與 Storybook 整合好，但需註冊雲端服務。拒絕（時程考量）。
- **Percy**：類似 Chromatic。拒絕。

**保留 Storybook 與否**：本 plan 暫不引入 Storybook（範圍守護）；若元件數成長到 50+ 再考
慮加入（屬未來 feature）。

---

## R12：效能監控 — web-vitals + 自寫 console log，是否引入 Sentry／Datadog RUM

**Decision**：使用 **web-vitals 3.5** 套件量測 LCP／CLS／INP，用 `console.log` 與 dev
overlay 顯示；**不**引入 Sentry／Datadog（生產級監控屬未來 feature）。

**Rationale**：
- 論文 demo 環境通常本機跑，遠端監控 overkill。
- web-vitals 體積極小（< 2 KB），可選擇性開啟（`?perf=1` query param）。
- Lighthouse CI 在 GitHub Actions 跑，已涵蓋 PR 階段的效能門檻檢查。

**Alternatives Considered**：
- **Sentry RUM**：需註冊、隱私／GDPR 評估。拒絕。
- **Datadog RUM**：商業服務，論文情境不適用。拒絕。

---

## 跨決策總結

| 主題 | 選擇 | 主要替代被拒原因 |
|------|------|-----------------|
| Chart 主軸 | Recharts | Plotly bundle 爆量、Victory 慢 |
| K 線 | lightweight-charts | ApexCharts 慢、自寫太貴 |
| 全域狀態 | React Query only | Redux/Zustand 重複造輪 |
| API codegen | openapi-typescript | Orval/hey-api 過度生成 |
| Mock | MSW | json-server 不支 SSE |
| i18n | react-i18next | LinguiJS babel macro 重 |
| CSS | Tailwind | CSS Modules 囉嗦 |
| Table | TanStack Table | AG Grid 太重 |
| Router | React Router 6 | TanStack Router 文件少 |
| Test | Vitest + Playwright | Jest ESM 差、Cypress 多瀏覽器弱 |
| 視覺迴歸 | Playwright snapshot | Chromatic／Percy 須註冊 |
| 效能監控 | web-vitals + Lighthouse CI | Sentry RUM 過度 |

**所有 NEEDS CLARIFICATION 已解決，可進入 Phase 1。**
