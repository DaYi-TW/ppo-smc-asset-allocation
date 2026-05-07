# Feature Specification: React War Room Dashboard

**Feature Branch**: `007-react-warroom`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 React 18+ TypeScript 戰情室前端，提供 PPO + SMC 系統決策視覺化儀表板：(1) 連續資產配置權重轉移圖、(2) 投資組合淨值曲線與回撤動態、(3) K 線圖疊加 SMC (FVG/OB/BOS) 標記。對應憲法 Principle IV 微服務解耦中 React 一層；消費 006 Spring Gateway 提供之 RESTful API 與 SSE 串流。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 即時資產配置視覺化（Priority: P1）

研究者完成 PPO 訓練後想觀察單一 episode 內三個資產板塊（Risk-On、Risk-Off、Cash）權重隨市場狀態變化的動態。前端 MUST 提供互動式 Stacked Area Chart：x 軸為交易日、y 軸為配置百分比（0-100%）、依攻擊型/避險型/現金堆疊；hover 顯示該日各標的（NVDA/AMD/TSM/MU/GLD/TLT/Cash）精確權重。論文撰寫亦可從此圖截圖支撐 Findings 章節。

**Why this priority**: 對應論文 Findings 主視覺證據；無此功能戰情室即不存在。也是研究者驗證模型行為的最低限度工具。

**Independent Test**: 啟動前端、登入後選擇「Episode Replay」頁、輸入既有 `episodeId`（從 006 取得），驗證 (a) Stacked Area Chart 渲染完整 8 年區間 ~2000 個資料點、(b) 滑鼠 hover 任意日期顯示 7 個資產的精確權重 tooltip、(c) 三板塊以憲法定義之顏色（Risk-On 紅、Risk-Off 綠、Cash 灰）區分。

**Acceptance Scenarios**:

1. **Given** 後端 006 已有 episode 結果，**When** 使用者導航至 `/episodes/<episodeId>`，**Then** 頁面 3 秒內渲染 Stacked Area Chart、軸標籤、legend，並可拖曳 brush selector 縮放時間範圍。
2. **Given** 圖表已渲染，**When** 使用者以滑鼠 hover 某交易日，**Then** 顯示 tooltip 含該日 ISO 8601 日期、7 個資產權重（百分比、4 位小數）、總權重 sum=1.0 驗證標記。

---

### User Story 2 - 淨值曲線與回撤監控（Priority: P1）

風控人員與論文審稿者需要快速評估 PPO 策略的風險特徵。前端 MUST 提供 NAV (Net Asset Value) 曲線圖與下方 Drawdown 區域圖（雙圖共享 x 軸）：NAV 圖顯示組合淨值（從 1.0 起算）；Drawdown 圖顯示 running max 至當前的回撤百分比（負值，紅色填充）；圖上標註關鍵事件（如 2020-03 COVID、2022-Q4 Fed 升息頂、2023 AI 行情起點）。

**Why this priority**: 憲法 Principle III 風險優先獎勵的視覺化驗證；論文 Findings 必須引用。屬論文核心圖表。

**Independent Test**: 同 episode 替換頁籤至「Risk View」，驗證 (a) NAV 曲線正確（最終值 ≈ 對應 SC-001 of 003），(b) Drawdown 圖最低點對齊 episode_log.summary.max_drawdown，(c) hover 顯示日期、NAV、drawdown 同步十字游標跨兩圖。

**Acceptance Scenarios**:

1. **Given** episode trajectory 已載入，**When** 切至 Risk View 頁籤，**Then** 上下兩圖共享時間軸、上圖以對數刻度切換、下圖填充紅色至負無窮、且最大回撤點以圓圈標記。
2. **Given** 多個 episodes 存在，**When** 使用者於同頁加選第二個 `episodeId`（不同 seed 或 ablation 組），**Then** 兩條 NAV 曲線疊加顯示、Drawdown 同樣疊加且半透明，便於 baseline vs SMC 對照。

---

### User Story 3 - K 線圖疊加 SMC 標記（Priority: P2）

SMC 特徵工程開發者與論文審稿者需要肉眼覆核「演算法判定的 BOS/CHoCh/FVG/OB 是否合理」。前端 MUST 提供 K 線圖（OHLC candlestick）並疊加：(a) BOS/CHoCh 標記（突破點以箭頭與標籤）、(b) FVG 區塊（淡色填充、標示 gap 上下界）、(c) OB 區塊（深色矩形、標示有效期內的支撐/壓力區）。標記資料源自 001 SMC 特徵引擎輸出（透過 006 暴露之 endpoint）。

**Why this priority**: 對應憲法 Principle II 特徵可解釋性「可在 K 線圖上視覺化驗證」之硬性要求；非實作則違憲。但相對 NAV/Weight P1 圖可後補。

**Independent Test**: 切至「SMC View」頁、選擇 `symbol=NVDA`、選擇日期區間 `2024-01-01` ~ `2024-06-30`，驗證 (a) K 線正確、(b) 該區間內 BOS 點以向上紅箭頭顯示、CHoCh 以向下綠箭頭、(c) FVG 區以淺藍填充、(d) OB 區以深藍矩形、(e) 點擊任一標記彈出 panel 顯示判定規則摘要與原始計算值。

**Acceptance Scenarios**:

1. **Given** 已選擇 NVDA 與日期區間，**When** 頁面渲染完成，**Then** 圖中 SMC 標記與後端回傳之 features JSON 一一對應（無漏標、無誤標）。
2. **Given** 使用者點擊某 FVG 區，**When** panel 彈出，**Then** 顯示三根 K 棒索引、gap 上下界、距當前價百分比、判定規則說明（連結至 docs）。

---

### User Story 4 - 即時推理串流與決策面板（Priority: P3）

維運人員與 demo 場景需要看到「PPO 模型對當前 obs 的即時決策」。前端 MUST 提供 Decision Panel：(a) 顯示當前選擇之 policy（含 git commit、訓練 final return）、(b) 一個 obs 輸入區（可由 006 即時抓最新行情或手動貼上 JSON）、(c) Submit 後顯示 action（7 個權重 bar chart）、value、log_prob、reward 各成分估計值；同時連接 SSE `/api/v1/tasks/{id}/stream` 顯示長 episode 的 progress bar。

**Why this priority**: demo 與監控需求；非論文核心。可在 P1/P2 完成後補上。

**Independent Test**: (a) 頁面顯示當前 policy metadata；(b) 點 Submit 按鈕、3 秒內顯示 action bar chart 與 reward 分解；(c) 開啟 episode run、進度條更新至 100% 後跳轉至 Replay 頁。

**Acceptance Scenarios**:

1. **Given** 006 已載入 policy `baseline_seed1`，**When** 使用者於 Decision Panel 點 Submit、obs 為合法 JSON，**Then** 顯示 7 個權重 bar、value 數值、log_prob、reward 三項成分（return / drawdown_penalty / turnover_penalty）。
2. **Given** 使用者發起 episode run，**When** SSE 推送 progress 事件，**Then** progress bar 平滑更新、完成後顯示「跳轉至結果」按鈕。

---

### Edge Cases

- **API 失敗（006 down）**：前端 MUST 顯示全頁錯誤橫幅 + 重試按鈕；不卡死、不白屏；圖表區塊顯示「Backend Unavailable」placeholder。
- **空資料**：episodeId 不存在或 trajectory 為空陣列 MUST 顯示「No data for this episode」並提供回首頁連結；不渲染空圖表。
- **大資料**：trajectory > 10000 個資料點 MUST 採前端 downsampling（LTTB 演算法或類似）至 ≤ 2000 點以避免瀏覽器卡頓；hover 仍以原始解析度查詢。
- **SSE 斷線**：自動重連 3 次（exponential backoff 1s/2s/4s）；3 次後顯示 toast「即時連線中斷」+ 手動重連按鈕。
- ~~**JWT 過期**：偵測 401 回應 MUST 自動重導至登入頁、保留原 deep link 為 `?next=` 參數。~~（[SCOPE-REDUCED]）
- **行動裝置**：頁寬 < 768px 時 MUST 採堆疊式 layout（圖表全寬、面板下移）；不要求完整 mobile UX，但須能讀。
- **顏色無障礙**：圖表色彩 MUST 滿足 WCAG AA 對比度，且提供 colorblind-safe palette 切換選項（紅綠色盲考量）。
- **時區處理**：前後端時間一律 UTC + ISO 8601；前端顯示時轉使用者 local 時區並標註原始 UTC tooltip。

## Requirements *(mandatory)*

### Functional Requirements

#### 路由與頁面結構

- **FR-001**: 系統 MUST 提供以下主要頁面：~~`/login`（JWT 登入）~~（[SCOPE-REDUCED]）、`/`（dashboard 摘要）、`/episodes`（episode 列表）、`/episodes/{id}`（episode replay，含 Weight / Risk / SMC 三 tab）、`/policies`（policy 列表與切換）、`/decision`（即時決策面板）、~~`/audit`（admin only：audit log 查詢）~~（[SCOPE-REDUCED]）。
- **FR-002**: 系統 MUST 採用 React Router v6+ 進行 client-side routing；URL 含完整狀態（episodeId、tab、時間區間 brush 範圍）以便分享連結。
- **FR-003** [SCOPE-REDUCED]: 系統 MUST 將未認證使用者導向 `/login`；登入成功後寫入 JWT 至 `httpOnly` cookie（若 006 支援）或 `sessionStorage`（fallback）。

#### 圖表元件

- **FR-004**: 系統 MUST 提供 `WeightStackedAreaChart` 元件：輸入 trajectory（含 weights × 7 assets × T 時間點），輸出可互動 stacked area chart；支援 brush 縮放、hover tooltip、legend 切換顯示。
- **FR-005**: 系統 MUST 提供 `NavDrawdownChart` 元件：上下雙圖共享 x 軸；NAV 圖支援線性/對數切換；Drawdown 圖以紅色面積填充至 y=0；最大回撤點以圓圈標記。
- **FR-006**: 系統 MUST 提供 `CandlestickWithSMCChart` 元件：K 線圖 + 4 種 SMC 標記層（BOS、CHoCh、FVG、OB）；每層可獨立切換顯示/隱藏；點擊標記彈出 detail panel。
- **FR-007**: 系統 MUST 提供 `ActionBarChart` 元件：7 個資產權重 bar、依憲法配色、總和標籤（驗證 sum=1.0 ± 1e-6）。
- **FR-008**: 圖表函式庫 MUST 採用 Recharts 或 D3（憲法 Tech Stack 已鎖定）；K 線採 lightweight-charts 或同等 OSS 函式庫；不引入需付費 license 之圖表。

#### 資料層與 API 整合

- **FR-009**: 系統 MUST 由 006 OpenAPI 規格自動生成 TypeScript client（openapi-typescript-codegen 或 orval）；client MUST 在 build time 失敗如果 schema 不一致。
- **FR-010**: 系統 MUST 採 React Query (TanStack Query) 管理 server state：含 query cache、stale-while-revalidate、自動重試（3 次 exp backoff）；不引入 Redux 等全域 state library。
- **FR-011**: 系統 MUST 提供 SSE client wrapper（封裝 EventSource）以消費 006 之 `/api/v1/tasks/{id}/stream`；含自動重連與 onError handler。
- **FR-012**: 系統 MUST 處理 trajectory blob 過大情境：若 006 回傳 `trajectoryUri`（pre-signed URL）則直接從物件儲存 fetch；若 inline 則直接用。

#### 認證與授權 [SCOPE-REDUCED 2026-05-04]

> **範圍調整說明**：檔次 2-local（單機 docker-compose 論文展示版）不含多用戶/JWT/Spring Security。FR-013–FR-015 暫時擱置，留作檔次 3 雲端部署時再啟用。前端 client 不送 `Authorization` header；亦不渲染 `/login` 頁面與 role-based 隱藏邏輯。
>
> 對應 task 標記為 `[SCOPE-REDUCED]` 不執行。

- **FR-013** [SCOPE-REDUCED]: 系統 MUST 在每個 API 請求附 `Authorization: Bearer <jwt>` header；JWT 過期時統一 redirect 至 `/login?next=<current>`。
- **FR-014** [SCOPE-REDUCED]: 系統 MUST 依 JWT role 顯示/隱藏功能：`reviewer` 看不到 Decision Panel 之 Submit 按鈕、看不到 Policy 載入按鈕、看不到 admin/audit 頁。
- **FR-015** [SCOPE-REDUCED]: 系統 MUST 在前端 attempt 任何 admin 操作前重新驗證 role；伺服器回 403 時顯示 friendly 錯誤訊息「需要研究者權限」。

#### UX 與無障礙

- **FR-016**: 系統 MUST 提供 dark mode 與 light mode 切換；首選由 OS-level prefers-color-scheme 偵測；切換狀態存入 localStorage。
- **FR-017**: 系統 MUST 提供色盲友善 palette 切換（normal / deuteranopia / protanopia）；圖表顏色由 theme provider 統一管理。
- **FR-018**: 全部互動元件 MUST 支援鍵盤操作（Tab navigation、Enter/Space 觸發、Arrow keys 圖表 brush）；通過 Lighthouse Accessibility ≥ 90 分。
- **FR-019**: 全部使用者文字 MUST 經 i18n（react-i18next）抽出；初版含 zh-TW（預設）、en-US 兩語系；可由右上角切換。
- **FR-020**: 系統 MUST 在所有 async 動作顯示 loading 狀態（skeleton screen 或 spinner）；網路錯誤顯示 retry button；無資料顯示 empty state illustration。

#### 效能與大資料

- **FR-021**: 系統 MUST 對 trajectory > 2000 點採 LTTB（Largest Triangle Three Buckets）downsampling；hover tooltip 仍查詢原始資料。
- **FR-022**: 系統 MUST 採 code splitting：每個主要路由獨立 bundle；首頁初始 JS bundle gzip 後 < 250 KB。
- **FR-023**: 系統 MUST 採 React.memo / useMemo 避免 trajectory 重渲染；圖表元件對相同 props 不應重繪（透過 React DevTools Profiler 驗證）。

#### 建構與部署

- **FR-024**: 系統 MUST 採 Vite 為 build tool；Node.js 版本 ≥ 18；提供 `npm run dev`、`npm run build`、`npm run preview`、`npm run test`、`npm run lint`、`npm run typecheck`。
- **FR-025**: 系統 MUST 提供 `Dockerfile`（多階段：node:18 build → nginx:alpine 託管 static assets）與 `nginx.conf`（含 SPA fallback、gzip、cache header、API proxy 至 006）。
- **FR-026**: 系統 MUST 支援透過 build-time 環境變數覆寫 API base URL：`VITE_API_BASE_URL`、`VITE_SSE_BASE_URL`、`VITE_AUTH_PROVIDER_URL`；不於 client bundle 內 hardcode 後端 URL。
- **FR-027**: 系統 MUST 採 ESLint + Prettier + TypeScript strict mode；CI 失敗如果 lint / typecheck / unit test 有錯。

#### 測試

- **FR-028**: 系統 MUST 採 Vitest + React Testing Library 撰寫元件單元測試；覆蓋率 ≥ 70%（圖表元件可豁免至 ≥ 50%，因 canvas 測試成本高）。
- **FR-029**: 系統 MUST 採 Playwright 撰寫 E2E 測試：登入流程、選擇 episode、檢視 Weight chart、切換 Risk view、檢視 SMC 標記、登出 — 至少 1 條 happy path 全程通過。
- **FR-030**: 系統 MUST 提供 mock API server（MSW, Mock Service Worker）：開發時可離線運作；E2E 測試亦可挑選 mock 或 live 模式。

#### 不在範圍內

- **FR-031**: 本 feature **不**做：訓練（004）、推理運算（005，僅消費）、Gateway/DB（006，僅消費）、SMC 計算（001，僅顯示其輸出）、即時下單接單、行動 app（僅 responsive web）、admin 設定 UI（policy 載入透過 006 直接 API；前端僅讀取顯示）。

### Key Entities

- **EpisodeViewModel**: 前端對單一 episode 的視角；包含 `episodeId`、`policyId`、`startDate`、`endDate`、`trajectoryUri`（lazy load）、`summary`（pre-fetch 含 finalReturn、maxDrawdown、sharpe）。
- **TrajectoryFrame**: trajectory 中單一時間點；`date`、`weights[7]`、`prices[6]`、`nav`、`drawdown`、`reward`。
- **SMCMarker**: K 線圖上單一標記；`type`（BOS/CHoCh/FVG/OB）、`startDate`、`endDate`（FVG/OB 為區間，BOS/CHoCh 為單點）、`metadata`（判定規則摘要）。
- **PolicyOption**: Policy 選擇器 dropdown 之選項；`policyId`、`displayName`、`finalMeanReturn`、`gitCommit`、`loadedAt`。
- **UserSession**: 已登入使用者；`userId`、`role`、`displayName`、`jwtExpiresAt`、`prefersDarkMode`、`prefersColorblindPalette`、`locale`。
- **ChartTheme**: 視覺化主題；`palette`（normal/deuteranopia/protanopia）、`mode`（dark/light）、`assetColors`（map symbol → hex）。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 從點選 episode 到 Stacked Area Chart 完整渲染（含 brush 可用）p95 < 3 秒（trajectory ~2000 點，本地網路）。
- **SC-002**: trajectory 10000 點仍可滑順互動（hover、brush 拖曳維持 ≥ 30 fps，Chrome DevTools Performance 驗證）。
- **SC-003**: 首頁初始 JS bundle gzip 後 < 250 KB；Lighthouse Performance ≥ 85 分（mobile 模式）、Accessibility ≥ 90 分。
- **SC-004**: K 線圖上 SMC 標記與 001 SMC 引擎輸出 100% 對齊（無漏、無誤標；E2E 測試比對 fixture）。
- **SC-005**: E2E happy path（登入 → 選 episode → 看 Weight → 切 Risk → 切 SMC → 登出）於 CI 一次通過、總執行時間 < 60 秒。
- **SC-006**: i18n 切換語系後所有可見文字更新、無 raw key 殘留；i18n key 完整度由 lint 規則檢查 ≥ 99%。
- **SC-007**: dark/light/colorblind 三種主題切換後圖表色彩正確套用、無 contrast 不足之元件（自動化 axe-core 測試）。
- **SC-008**: 元件單元測試覆蓋率 ≥ 70%；圖表元件 ≥ 50%；CI 強制門檻。
- **SC-009**: 後端 006 down 時前端不白屏、不 crash；顯示明確錯誤橫幅與重試按鈕（手動驗證 + Playwright 測試）。
- **SC-010**: TypeScript strict mode 全綠（含 `noImplicitAny`、`strictNullChecks`、`noUnusedLocals`）；CI 強制 `tsc --noEmit` 通過。

## Assumptions

- 006 Spring Gateway 已實作完成、提供穩定 OpenAPI 3.1 規格與 JWT 認證；本 feature 不重新發明 auth provider。
- 005 inference service 不直接被前端呼叫；所有後端通訊一律經 006（憲法 Principle IV 微服務拓撲）。
- 001 SMC feature engine 之輸出（FVG/OB/BOS 標記）由 006 暴露端點供查詢；本 feature 不重算 SMC。
- 部署目標為現代瀏覽器（Chrome/Edge/Firefox/Safari 最新兩版）；不支援 IE 11。
- 使用者人數尺度為個位數研究者 + 個位數審稿者；不需 SSR / CDN edge cache 等高並發優化。
- 顏色配置：Risk-On 紅色系（#E53935 系列）、Risk-Off 綠色系（#43A047 系列）、Cash 灰色（#757575）；個別標的以同色系深淺區分；與論文圖表色彩一致。
- 部署採容器化（與 006 同 K8s cluster），透過 ingress 共享 domain 之不同 path 提供。
- 本 feature 不做使用者註冊（僅登入既有帳號，由 IDP 預先建立）；不做密碼重設。
- 圖表函式庫優先選 Recharts（憲法允許），互動式 K 線採 lightweight-charts；若 Recharts 對堆疊圖效能不足則改 D3，於 plan 階段評估。
- 多語系初版僅 zh-TW + en-US；其他語系（ja、ko）為未來 feature。
