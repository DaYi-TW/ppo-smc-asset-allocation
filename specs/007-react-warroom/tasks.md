# Tasks: 戰情室前端（React War Room）

**Input**: Design documents from `/specs/007-react-warroom/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/*.md, quickstart.md

**Tests**: 包含於本任務清單（spec FR-021 要求 unit + e2e 覆蓋）。所有測試於 `apps/warroom/tests/` 與 `apps/warroom/src/test/`。

**Organization**: Tasks 按 user story 分組，支援獨立實作與測試。

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行（不同檔案、無相依）
- **[Story]**：US1=Overview 權重+NAV、US2=Trajectory K 線+SMC、US3=Decision 面板、US4=Settings／偏好
- 所有路徑為相對 repo root

---

## Path Conventions

- App root：`apps/warroom/`
- Source：`apps/warroom/src/`
- Tests：`apps/warroom/src/test/`（unit fixtures、MSW）、`apps/warroom/tests/`（unit、component、e2e）

---

## Phase 1: Setup（共用基礎建設）

- [ ] T001 建立 `apps/warroom/` 並初始化 Vite + React 18 + TypeScript（`npm create vite@latest -- --template react-ts`）
- [ ] T002 在 `apps/warroom/.nvmrc` 鎖定 Node `18.20.x`；於 `apps/warroom/package.json` 加 `engines.node: ">=18.20 <19"`
- [ ] T003 [P] 安裝核心 deps：react-router-dom@6、@tanstack/react-query@5、recharts@2、lightweight-charts@4、d3-scale、d3-array、zod@3
- [ ] T004 [P] 安裝 dev deps：vitest@1、@testing-library/react@14、playwright@1.43、msw@2、@types/d3-scale、@types/d3-array、openapi-typescript@7、tailwindcss@3.4、@tailwindcss/forms、postcss、autoprefixer、eslint、@typescript-eslint/*、prettier、husky、lint-staged
- [ ] T005 [P] 設定 `apps/warroom/tsconfig.json`：`strict: true`、`noUncheckedIndexedAccess: true`、`exactOptionalPropertyTypes: true`、`noImplicitOverride: true`、`paths` 別名 `@/*` → `./src/*`
- [ ] T006 [P] 設定 `apps/warroom/vite.config.ts`：別名與 vitest 整合、build 輸出到 `dist/`、開啟 build manifest
- [ ] T007 [P] 設定 `apps/warroom/tailwind.config.ts` 與 `postcss.config.cjs`，引入 `theme/tailwind-preset.ts`（暫放佔位）
- [ ] T008 [P] 設定 `apps/warroom/.eslintrc.cjs`：禁用 `@typescript-eslint/no-explicit-any`、開啟 `react-hooks/exhaustive-deps`、整合 prettier
- [ ] T009 [P] 設定 `apps/warroom/.prettierrc`：印刷寬 100、單引號、無分號（或專案習慣）
- [ ] T010 [P] 設定 `apps/warroom/playwright.config.ts`：base URL `http://localhost:5173`、webServer 啟動 dev、視覺快照基準
- [ ] T011 [P] 設定 `apps/warroom/vitest.config.ts`：jsdom 環境、`src/test/setup.ts` 載入 MSW
- [ ] T012 [P] 建立 `apps/warroom/.env.example`：`VITE_USE_MOCK=true`、`VITE_API_BASE_URL=http://localhost:8080`、`VITE_DEMO_JWT=`
- [ ] T013 [P] 建立 `apps/warroom/README.md` 摘要 quickstart 重點
- [ ] T014 [P] 設定 husky pre-commit：lint + typecheck（不跑測試以確保提交速度）
- [ ] T015 [P] 建立 GitHub Actions workflow `.github/workflows/web.yml`：跑 `npm ci → lint → typecheck → test:run → test:e2e:ci → build → gen:check → i18n:check → lighthouse`

---

## Phase 2: Foundational（所有 user story 都依賴的核心元件，無 story label）

⚠️ Phase 2 必須完成才能開始任何 user story。

- [ ] T016 在 `apps/warroom/src/api/client.ts` 實作 fetch wrapper：自動注入 `Authorization`、`Idempotency-Key` header；錯誤統一轉 `ApiErrorViewModel`
- [ ] T017 在 `apps/warroom/src/api/queryKeys.ts` 集中匯出 React Query key factories（`episodeKeys`、`policyKeys`、`auditKeys`）
- [ ] T018 在 `apps/warroom/src/api/types.gen.ts` 跑首次 codegen（從 stub `gateway-openapi.yaml`；後續由 006 完成後重跑）
- [ ] T019 在 `apps/warroom/src/api/envelopes.ts` 實作 DTO ↔ ViewModel 轉換函式（toEpisodeSummary、toEpisodeDetail、toTrajectoryFrame、toSMCMarker、toRewardSeries、toApiError）
- [ ] T020 在 `apps/warroom/src/api/sse.ts` 實作 EventSource wrapper：retry 指數退避、unmount cleanup、reconnect API
- [ ] T021 在 `apps/warroom/src/api/errorMap.ts` 建立 `errorCodeToI18nKey` 與 `resolveErrorMessage()`（對齊 contracts/i18n-keys.md）
- [ ] T022 [P] 在 `apps/warroom/src/viewmodels/episode.ts` 定義 `EpisodeSummaryViewModel`、`EpisodeDetailViewModel`、`EpisodeStatus`
- [ ] T023 [P] 在 `apps/warroom/src/viewmodels/trajectory.ts` 定義 `TrajectoryFrame`、`WeightAllocation`、`OHLCV`、`ActionVector`
- [ ] T024 [P] 在 `apps/warroom/src/viewmodels/smc.ts` 定義 `SMCSignals`、`SMCMarker`、`SMCMarkerKind`
- [ ] T025 [P] 在 `apps/warroom/src/viewmodels/reward.ts` 定義 `RewardSnapshot`、`RewardSeries`、`RewardCumulativePoint`
- [ ] T026 [P] 在 `apps/warroom/src/viewmodels/error.ts` 定義 `ApiErrorViewModel`
- [ ] T027 [P] 在 `apps/warroom/src/viewmodels/policy.ts` 定義 `PolicyOption`、`UserPreferences`
- [ ] T028 在 `apps/warroom/src/theme/tokens.ts` 定義 token 物件（亮／暗各一份，導出供 chart 使用）
- [ ] T029 在 `apps/warroom/src/theme/tailwind-preset.ts` 把 token 對應為 Tailwind theme.extend
- [ ] T030 在 `apps/warroom/src/theme/applyTheme.ts` 實作 `applyTheme(theme)` 與 system 主題監聽
- [ ] T031 在 `apps/warroom/src/theme/getChartTheme.ts` 實作 runtime 讀 CSS variable 給 Recharts／lightweight-charts 用
- [ ] T032 在 `apps/warroom/src/i18n/index.ts` 初始化 i18next（zh-TW 為 fallback、URL `?lng=` 也支援）
- [ ] T033 [P] 建立 `apps/warroom/src/i18n/zh-TW.json`（complete keys per contracts/i18n-keys.md）
- [ ] T034 [P] 建立 `apps/warroom/src/i18n/en.json`（complete keys per contracts/i18n-keys.md）
- [ ] T035 [P] 在 `apps/warroom/src/utils/format.ts` 實作 `formatUSD`、`formatPercent`、`formatNumber`、`formatDate`、`formatDateTime`
- [ ] T036 [P] 在 `apps/warroom/src/utils/chart-helpers.ts` 實作 `clamp`、`buildSMCMarkers(trajectory)`、`computeDrawdownSeries(navSeries)`
- [ ] T037 在 `apps/warroom/src/components/common/ErrorBoundary.tsx` 實作錯誤邊界（含 traceId 顯示與 retry）
- [ ] T038 [P] 在 `apps/warroom/src/components/common/LoadingSkeleton.tsx` 實作多種 variant（chart、table、card）
- [ ] T039 [P] 在 `apps/warroom/src/components/common/EmptyState.tsx` 實作空態元件
- [ ] T040 在 `apps/warroom/src/components/layout/AppShell.tsx` 實作 layout（TopBar + SideNav + main）
- [ ] T041 [P] 在 `apps/warroom/src/components/layout/TopBar.tsx` 實作頂部列（含 policy switcher、語言切換、主題切換）
- [ ] T042 [P] 在 `apps/warroom/src/components/layout/SideNav.tsx` 實作側欄（4 個頁面 link、響應式收合）
- [ ] T043 在 `apps/warroom/src/App.tsx` 設定 React Router（`createHashRouter` + 4 routes + 404）
- [ ] T044 在 `apps/warroom/src/main.tsx` 整合 React Query Provider、i18n Provider、theme 初始化、MSW 啟動（dev 模式）
- [ ] T045 在 `apps/warroom/src/test/setup.ts` 設定 vitest jsdom + MSW server
- [ ] T046 [P] 在 `apps/warroom/src/test/fixtures/episode-list.json` 建立 episode list fixture（10 筆）
- [ ] T047 [P] 在 `apps/warroom/src/test/fixtures/episode-detail.json` 建立 episode detail fixture（含 1000 frames trajectory）
- [ ] T048 [P] 在 `apps/warroom/src/test/fixtures/policies.json` 建立 policy list fixture（3 筆）
- [ ] T049 在 `apps/warroom/src/test/mocks/handlers.ts` 實作所有 OpenAPI 端點的 MSW handler（含成功與錯誤情境）
- [ ] T050 在 `apps/warroom/src/test/mocks/browser.ts` 建立 service worker for dev mock 模式
- [ ] T051 [P] 在 `apps/warroom/tests/unit/format.test.ts` 撰寫 format util 單元測試
- [ ] T052 [P] 在 `apps/warroom/tests/unit/envelopes.test.ts` 撰寫 envelope 轉換測試（每個函式 happy + edge case）
- [ ] T053 [P] 在 `apps/warroom/tests/unit/chart-helpers.test.ts` 撰寫 chart helper 測試（drawdown 計算、SMC marker 生成）

---

## Phase 3: User Story 1 — Overview 權重 + NAV/drawdown（P1）

**Goal**：使用者進入戰情室首頁可立即看到當前 policy 的權重分配與淨值表現。

**Independent Test**：在 `/overview` 頁載入 mock fixture，可看到 stacked-area 與 NAV/drawdown 雙軸圖；切換 policy 時資料更新；hover tooltip 顯示正確日期與數值。

- [ ] T054 [P] [US1] 在 `apps/warroom/src/hooks/usePolicies.ts` 實作 React Query hook
- [ ] T055 [P] [US1] 在 `apps/warroom/src/hooks/useEpisodeList.ts` 實作 hook（接受 filters）
- [ ] T056 [P] [US1] 在 `apps/warroom/src/hooks/useEpisodeDetail.ts` 實作 hook
- [ ] T057 [US1] 在 `apps/warroom/src/components/charts/WeightStackedArea.tsx` 實作權重 stacked-area chart（Recharts）
- [ ] T058 [US1] 在 `apps/warroom/src/components/charts/NavDrawdownChart.tsx` 實作 NAV + drawdown 雙軸 line chart（Recharts ComposedChart）
- [ ] T059 [P] [US1] 在 `apps/warroom/src/components/panels/PolicyPicker.tsx` 實作 policy 切換下拉
- [ ] T060 [P] [US1] 在 `apps/warroom/src/components/panels/EpisodeMeta.tsx` 顯示 totalReturn、Sharpe、maxDrawdown summary cards
- [ ] T061 [US1] 在 `apps/warroom/src/routes/overview.tsx` 組合 PolicyPicker + WeightStackedArea + NavDrawdownChart + EpisodeMeta；URL state 同步 `policyId`
- [ ] T062 [P] [US1] 在 `apps/warroom/tests/component/WeightStackedArea.test.tsx` 撰寫 component 測試
- [ ] T063 [P] [US1] 在 `apps/warroom/tests/component/NavDrawdownChart.test.tsx` 撰寫 component 測試
- [ ] T064 [P] [US1] 在 `apps/warroom/tests/component/PolicyPicker.test.tsx` 撰寫 component 測試
- [ ] T065 [US1] 在 `apps/warroom/tests/e2e/overview.spec.ts` 撰寫 e2e：載入 → 切換 policy → 圖表更新 → tooltip 驗證
- [ ] T066 [P] [US1] 在 `apps/warroom/tests/e2e/visual/overview.spec.ts` 加入視覺快照（亮／暗主題各一張）

**Checkpoint**：US1 完成 — 可獨立 demo Overview 頁。

---

## Phase 4: User Story 2 — Trajectory K 線 + SMC 標記（P1）

**Goal**：使用者可在 K 線圖上肉眼驗證 SMC 特徵（BOS/CHoCh/FVG/OB），滿足憲法 Principle II。

**Independent Test**：在 `/trajectory?episodeId=...` 頁載入 fixture，K 線渲染 < 3s；BOS/CHoCh 箭頭出現在正確位置；FVG/OB 矩形可被切換顯隱；hover tooltip 顯示判定規則。

- [ ] T067 [P] [US2] 在 `apps/warroom/src/hooks/useTrajectory.ts` 實作 trajectory query hook
- [ ] T068 [US2] 在 `apps/warroom/src/components/charts/KLineWithSMC.tsx` 用 lightweight-charts 渲染 K 線（含 zoom/pan）
- [ ] T069 [US2] 在 `apps/warroom/src/components/charts/KLineWithSMC.tsx` 加入 SMC overlay：BOS/CHoCh 用 `setMarkers()`、FVG/OB 用上層 canvas + D3
- [ ] T070 [P] [US2] 在 `apps/warroom/src/components/panels/SMCFilter.tsx` 實作 BOS/CHoCh/FVG/OB 顯隱 toggle
- [ ] T071 [P] [US2] 在 `apps/warroom/src/components/panels/EpisodePicker.tsx` 從 list 切到指定 episode（或從 URL 帶入）
- [ ] T072 [US2] 在 `apps/warroom/src/routes/trajectory.tsx` 組合 KLine + SMCFilter + EpisodePicker；URL state 同步 zoom/from/to/showSMC
- [ ] T073 [P] [US2] 在 `apps/warroom/tests/component/KLineWithSMC.test.tsx` 測試 marker 渲染數量（BOS markers count == fixture 數量）
- [ ] T074 [P] [US2] 在 `apps/warroom/tests/component/SMCFilter.test.tsx` 測試 toggle 行為
- [ ] T075 [US2] 在 `apps/warroom/tests/e2e/trajectory.spec.ts` 撰寫 e2e：選 episode → 圖表渲染 → 縮放互動 → SMC filter 切換
- [ ] T076 [P] [US2] 在 `apps/warroom/tests/e2e/visual/trajectory.spec.ts` 加入視覺快照

**Checkpoint**：US2 完成 — 可獨立 demo K 線 + SMC 標記。

---

## Phase 5: User Story 3 — Decision 面板（P2）

**Goal**：審查者可逐步檢視 policy 在某時點的決策依據（觀測值、動作、reward 分解），含即時 SSE 推論模式。

**Independent Test**：在 `/decision?episodeId=...&step=42` 顯示完整觀測值表格、action vector、reward stacked bar、自然語言敘述；切到 `?live=1` 模式可看到 SSE 流即時更新。

- [ ] T077 [P] [US3] 在 `apps/warroom/src/hooks/useEpisodeStream.ts` 實作 SSE hook（含 reconnect、status state）
- [ ] T078 [P] [US3] 在 `apps/warroom/src/hooks/useInfer.ts` 實作 mutation hook（含 idempotency key）
- [ ] T079 [P] [US3] 在 `apps/warroom/src/components/panels/ObservationTable.tsx` 用 TanStack Table 渲染觀測值
- [ ] T080 [P] [US3] 在 `apps/warroom/src/components/panels/ActionVector.tsx` 顯示 raw + normalized + logProb + entropy
- [ ] T081 [US3] 在 `apps/warroom/src/components/charts/RewardBreakdown.tsx` 實作 stacked bar（單步）+ line（累積）
- [ ] T082 [P] [US3] 在 `apps/warroom/src/components/panels/DecisionNarration.tsx` 從觀測 + action 生成自然語言敘述（用 i18n template）
- [ ] T083 [US3] 在 `apps/warroom/src/routes/decision.tsx` 組合面板；支援模式 A（episodeId+step）與模式 B（policyId+live）
- [ ] T084 [P] [US3] 在 `apps/warroom/tests/component/RewardBreakdown.test.tsx` 撰寫 component 測試
- [ ] T085 [P] [US3] 在 `apps/warroom/tests/component/ObservationTable.test.tsx` 撰寫 component 測試
- [ ] T086 [P] [US3] 在 `apps/warroom/tests/component/DecisionNarration.test.tsx` 測試敘述模板插值
- [ ] T087 [US3] 在 `apps/warroom/tests/e2e/decision.spec.ts` 撰寫 e2e：載入歷史 → 切換 step → 切到 live 模式 → SSE 連線
- [ ] T088 [P] [US3] 在 `apps/warroom/tests/e2e/visual/decision.spec.ts` 加入視覺快照

**Checkpoint**：US3 完成 — 可獨立 demo 決策面板。

---

## Phase 6: User Story 4 — Settings／偏好（P3）

**Goal**：使用者可調整語言、主題、預設 policy、時區，設定保存於 localStorage 並跨頁同步。

**Independent Test**：進 `/settings` 改語言 → 整 UI 立即翻譯（無 reload）；改主題 → 立即套用；refresh 後設定保留。

- [ ] T089 [P] [US4] 在 `apps/warroom/src/hooks/useUserPrefs.ts` 實作 localStorage-backed 偏好設定 hook
- [ ] T090 [P] [US4] 在 `apps/warroom/src/hooks/useTheme.ts` 整合 useUserPrefs + applyTheme + system 監聽
- [ ] T091 [US4] 在 `apps/warroom/src/routes/settings.tsx` 實作四個設定欄位（語言、主題、預設 policy、時區）
- [ ] T092 [P] [US4] 在 `apps/warroom/tests/component/Settings.test.tsx` 測試切換語言／主題的副作用
- [ ] T093 [US4] 在 `apps/warroom/tests/e2e/settings.spec.ts` 撰寫 e2e：切換語言 → UI 翻譯 → 切主題 → reload 後保留

**Checkpoint**：US4 完成 — 全 4 條 user story 可獨立 demo。

---

## Phase 7: Polish & Cross-Cutting

- [ ] T094 [P] 在 `apps/warroom/package.json` 加 npm scripts：`gen:api`、`gen:check`、`i18n:check`、`lighthouse`、`test:e2e:ci`、`preview`
- [ ] T095 [P] 設定 Lighthouse CI（`@lhci/cli`）門檻：performance ≥ 85、accessibility ≥ 90
- [ ] T096 [P] 設定 vite 的 manual chunks：將 lightweight-charts 分到獨立 chunk（lazy load 於 trajectory route）
- [ ] T097 確認 main bundle gzipped ≤ 250 KB（跑 `vite-bundle-visualizer` 驗證；不過則 tree-shake／lazy-load）
- [ ] T098 [P] 加入 Web Vitals 量測（`web-vitals` 套件，dev mode console log）
- [ ] T099 [P] 在 `apps/warroom/src/components/common/ErrorBoundary.tsx` 加上「複製 traceId」按鈕
- [ ] T100 [P] 確認 a11y：跑 `pa11y-ci`，所有頁面 WCAG AA 通過（對比、ARIA、focus order）
- [ ] T101 [P] 加入 keyboard shortcut：`?` 開啟快捷鍵說明 modal（hot path 必要功能不放快捷，避免 11ty 風險）
- [ ] T102 補完 `apps/warroom/README.md`（含 quickstart 連結、scripts 對照表）
- [ ] T103 在 docs/ 連結 7 個本 spec 工件至 README 主索引（與 004/005/006 一致）
- [ ] T104 跑完整 CI 流程驗證：`npm ci → lint → typecheck → test:run → test:e2e:ci → build → gen:check → i18n:check → lighthouse` 全綠
- [ ] T105 視覺迴歸 baseline 建立：commit 所有 `tests/e2e/visual/__screenshots__/*.png`

---

## Dependencies & Execution Order

### Phase 之間
- Phase 1（Setup）→ 必須完成才能進 Phase 2
- Phase 2（Foundational）→ 必須完成才能進 Phase 3 ~ 6
- Phase 3-6（User Stories）→ 各自獨立，建議按 US1 → US2 → US3 → US4 順序但可平行
- Phase 7（Polish）→ 在 P1（US1+US2）完成後即可開始部分項目（如 T094 ~ T097）

### User Story 內部
- Hooks（T054-T056、T067、T077-T078、T089-T090）先於使用它們的 components／routes
- Components 先於 routes 組合
- 測試與實作可平行（test [P] 與對應 component 不同檔案）

---

## Parallel Execution Examples

### Setup Phase（T003-T015 可並行）

```
Agent A: T003 install runtime deps
Agent B: T004 install dev deps
Agent C: T005 tsconfig
Agent D: T006 vite config
Agent E: T007 tailwind config
Agent F: T008 eslint
Agent G: T015 GitHub Actions
```

### Foundational viewmodels（T022-T027）

```
Agent A: T022 episode.ts
Agent B: T023 trajectory.ts
Agent C: T024 smc.ts
Agent D: T025 reward.ts
Agent E: T026 error.ts
Agent F: T027 policy.ts
```

### User Story 1 平行（T054-T056、T062-T064、T066）

```
Agent A: T054 usePolicies
Agent B: T055 useEpisodeList
Agent C: T056 useEpisodeDetail
[完成後]
Agent D: T057 WeightStackedArea
Agent E: T058 NavDrawdownChart
Agent F: T059 PolicyPicker
Agent G: T060 EpisodeMeta
[完成後]
Agent H: T061 overview route
Agent I: T062-T064 component tests
Agent J: T066 visual snapshot
```

---

## Implementation Strategy

### MVP 範圍
- Setup（Phase 1）+ Foundational（Phase 2）+ US1（Phase 3）= 可 demo 戰情室基本樣貌
- 約 66 tasks（T001-T066）

### Incremental Delivery
1. **MVP**：完成 US1，可 demo 給審查者看「戰情室能跑起來」
2. **+US2**：加上 K 線 + SMC（Principle II 落實），是論文核心 demo
3. **+US3**：加上 Decision 面板（風險優先 reward 視覺驗證）
4. **+US4**：加上 Settings（體驗完整化）
5. **Polish**：Lighthouse、a11y、bundle size、視覺快照

### 關鍵風險
- **K 線 + SMC overlay**（T068-T069）：lightweight-charts custom layer 是技術未知，建議
  Phase 4 開始前先做 spike（半天）驗證可行性。
- **OpenAPI codegen**（T018）：依賴 006 的 yaml dump；若 006 未完成可先用手寫 stub yaml
  跑 codegen 不阻塞前端開發。
- **視覺快照跨機器**（T066、T076、T088）：建議 CI 用 Docker（mcr.microsoft.com/playwright）
  確保字型與 GPU 一致。

---

**Total tasks: 105**
**US1 tasks: 13（T054-T066）**
**US2 tasks: 10（T067-T076）**
**US3 tasks: 12（T077-T088）**
**US4 tasks: 5（T089-T093）**
**Setup + Foundational: 53（T001-T053）**
**Polish: 12（T094-T105）**

**Format validation**：所有 105 tasks 均符合 `- [ ] T### [P?] [USx?] description with file path` 格式。
