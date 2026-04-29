# Quickstart：戰情室前端開發

**Feature**: 007-react-warroom
**Date**: 2026-04-29

讓新進開發者在 5 分鐘內跑起前端 dev server，熟悉 mock 模式、e2e 測試與 build 流程。

---

## 前置需求

- Node.js **18.20.x**（透過 `.nvmrc` 鎖定）。建議用 `nvm`：
  ```bash
  nvm install 18.20
  nvm use
  ```
- npm 10+
- （可選）已 build 並啟動的 006 Spring Gateway（`http://localhost:8080`）；若未啟動可用
  mock 模式跑前端。
- （e2e 測試用）Playwright browsers：`npx playwright install --with-deps`

---

## 1. 安裝相依

```bash
cd apps/warroom
npm ci         # 嚴格依 package-lock.json 安裝（CI 等價）
```

驗證 lock file 未漂移：

```bash
git status              # 不應出現 package-lock.json 變更
```

---

## 2. 第一次啟動（Mock 模式）

最快驗證流程的方式是 mock 模式，不需要任何後端：

```bash
# 環境變數
cp .env.example .env.development.local
# 確認 .env.development.local 包含：
#   VITE_USE_MOCK=true
#   VITE_API_BASE_URL=http://localhost:5173/api  # mock 模式 base url 不重要

npm run dev
# 開啟 http://localhost:5173
```

預期：
- Console 顯示 `[MSW] Mocking enabled.`
- 頁面導向 `/overview`，看到權重分配 stacked-area 與 NAV/drawdown 雙線圖
- 無錯誤 toast、無 console.error

---

## 3. 連線實際後端模式

如果 006 Gateway 已在 `localhost:8080` 運行：

```bash
# .env.development.local 改為：
#   VITE_USE_MOCK=false
#   VITE_API_BASE_URL=http://localhost:8080
#   VITE_DEMO_JWT=<付給你的 dev-only JWT>

npm run dev
```

驗證：
1. 打開瀏覽器 DevTools → Network。
2. 應看到 `GET /api/v1/policies` 回 200。
3. Overview 頁顯示真實的 episode list。

無 JWT 時的快速產生（dev only）：

```python
# scripts/dev/issue-dev-jwt.py（在 006 倉庫）
# 產生有效 24 小時的 HS256 JWT，貼到 VITE_DEMO_JWT
```

---

## 4. 跑單元測試

```bash
npm run test            # vitest watch 模式
npm run test:run        # 執行一次（CI 等價）
npm run test:coverage   # 含覆蓋率報告
```

預期：
- 至少 X 個 test suite 通過（隨實作進度增加）
- coverage：lines ≥ 85%、branches ≥ 75%

執行單一測試：

```bash
npm run test -- src/utils/format.test.ts
```

---

## 5. 跑 e2e 測試（Playwright）

確保 dev server 已開：

```bash
# Terminal 1
npm run dev

# Terminal 2
npm run test:e2e
```

或讓 Playwright 自動啟動 dev server：

```bash
npm run test:e2e:ci    # 內部使用 webServer config 自動啟停
```

執行單一 spec：

```bash
npx playwright test tests/e2e/overview.spec.ts
```

更新視覺快照（必要時）：

```bash
npx playwright test --update-snapshots
git add tests/e2e/visual/__screenshots__/  # commit 進 repo
```

---

## 6. 型別生成（OpenAPI codegen）

當 006 Gateway 的 `openapi.yaml` 變更後：

```bash
# 假設 006 已將更新的 yaml dump 到 .specify/extensions/openapi/gateway-openapi.yaml
npm run gen:api
git diff src/api/types.gen.ts   # 檢視差異
```

CI 會自動跑 `npm run gen:check` 驗證 types.gen.ts 與 yaml 一致；不一致即 fail。

---

## 7. Lint 與 typecheck

```bash
npm run lint          # ESLint + Prettier
npm run lint:fix      # 自動修復可修復的 issue
npm run typecheck     # tsc --noEmit
```

CI 會跑這三項；本機 commit 前建議先跑。

---

## 8. Production build 與本機預覽

```bash
npm run build
# 輸出至 dist/
# Build 完成 console 顯示 chunk 大小，main 應 ≤ 250 KB gzipped

npm run preview
# 在 http://localhost:4173 預覽 production build
```

驗證 bundle 大小：

```bash
npx vite-bundle-visualizer  # 啟動可視化 bundle 分析（webpack-bundle-analyzer 等價物）
```

---

## 9. Lighthouse 效能驗證

```bash
npm run lighthouse        # 會啟動 preview server 並跑 Lighthouse
```

預期：
- Performance ≥ 85
- Accessibility ≥ 90
- Best Practices ≥ 90
- SEO（純 SPA 無 SSR）：可低，無硬性要求

CI 同樣會跑 Lighthouse CI（`@lhci/cli`），門檻不通過則 fail。

---

## 10. 4 條 user story 的手動驗證流程

### US1：權重分配 + NAV/drawdown（Overview 頁）

1. 啟動 `npm run dev`（mock 或真實後端皆可）
2. 進入 `/overview`
3. 切換 policy 下拉選單，圖表應在 < 1s 內更新
4. hover NAV 線上某點，tooltip 應顯示日期與淨值
5. drawdown 線必須與 NAV 線共軸但用第二 y 軸（紅色）

### US2：K 線圖 + SMC 標記（Trajectory 頁）

1. 從 Overview 點擊任一 episode 進入 `/trajectory?episodeId=...`
2. 圖表載入後應在 < 3s 內完成首次渲染
3. 拖拉時間軸縮放 — 互動應 ≥ 30 fps（DevTools Performance tab 驗證）
4. 點 SMC 過濾器只顯示「FVG」，其他箭頭應消失
5. hover BOS 箭頭，tooltip 應顯示判定規則與時間
6. URL 應反映縮放範圍（`?zoomStart=...&zoomEnd=...`）

### US3：決策面板（Decision 頁）

1. 進入 `/decision?episodeId=...&step=42`
2. 觀測值表格應列出所有特徵（含 SMC 訊號）
3. Action vector 顯示原始與 normalized 兩排數值
4. Reward breakdown stacked-bar 顯示 returnComponent / drawdownPenalty / costPenalty
5. 自然語言敘述：應呈現「模型於 YYYY-MM-DD 採取動作 X：因 Y」格式

### US4：偏好設定（Settings 頁）

1. 進入 `/settings`
2. 切換語言 zh-TW → en，整個 UI 應立即翻譯（無 reload）
3. 切換主題 light → dark → system
4. 切換預設 policy
5. 切到 system 主題時，作業系統暗色模式變更應自動同步

---

## 11. 常見問題排查

| 症狀                                    | 可能原因                                       | 解法                                                 |
|-----------------------------------------|------------------------------------------------|------------------------------------------------------|
| `[MSW] Mocking enabled` 但 API 還是真打 | service worker 未啟動                          | 清空 site data → `npm run dev` 重啟                  |
| Lighthouse Performance < 85             | bundle 過大／圖表渲染阻塞                      | 跑 `vite-bundle-visualizer` 找 hot chunk             |
| `npm run gen:check` 在 CI fail          | 006 OpenAPI yaml 已更新但本地 types.gen.ts 沒同步 | `npm run gen:api` 後 commit                          |
| Playwright snapshot 有差異              | 字型 render 跨機器不一致                       | 用 Docker 跑 e2e（`docker run mcr.microsoft.com/playwright`）|
| TypeScript 抱怨 `any`                   | 通常是 chart 元件 prop                         | 用 `as ChartTheme` 型別斷言或補 `unknown` 中介       |

---

## 12. 提交前檢查清單

```bash
npm run lint
npm run typecheck
npm run test:run
npm run test:e2e:ci
npm run build
npm run gen:check
npm run i18n:check
```

全部通過後再 commit。本地 husky pre-commit 會跑前 3 項；CI 會跑所有 7 項。

---

## 13. 結構速查

```
apps/warroom/src/
├── routes/        # 4 個頁面
├── components/    # chart / panel / layout / common
├── hooks/         # 12 個 React Query hook
├── api/           # client、types.gen、envelopes、queryKeys
├── viewmodels/    # TypeScript 介面定義
├── i18n/          # zh-TW + en
├── theme/         # token + tailwind preset
├── utils/         # format、chart helpers
└── test/          # MSW handler + fixture + setup
```

完整檔案樹見 [plan.md → Project Structure](./plan.md#project-structure)。
