# UI Routes Contract

**Feature**: 007-react-warroom
**Date**: 2026-04-29

定義戰情室前端的路由結構、layout 階層與 URL state 規約。所有路由採 hash routing
（`createHashRouter`），URL 形式為 `https://warroom.example.com/#/<page>?<query>`。

---

## 路由總表

| Path                        | Page Component               | Title (zh-TW)        | Title (en)              | Layout    |
|-----------------------------|------------------------------|----------------------|-------------------------|-----------|
| `/`                         | redirect → `/overview`       | —                    | —                       | —         |
| `/overview`                 | `routes/overview.tsx`        | 戰情總覽             | Overview                | AppShell  |
| `/trajectory`               | `routes/trajectory.tsx`      | 軌跡分析             | Trajectory Analysis     | AppShell  |
| `/decision`                 | `routes/decision.tsx`        | 決策面板             | Decision Panel          | AppShell  |
| `/settings`                 | `routes/settings.tsx`        | 偏好設定             | Settings                | AppShell  |
| `*`                         | `routes/not-found.tsx`       | 404                  | 404                     | AppShell  |

---

## URL Query State 規約

### `/overview`

```
?policyId=<uuid>          # 切換顯示哪個 policy 的 episode list（預設：active policy）
```

預期行為：
- 若無 `policyId`：自動取 `GET /api/v1/policies` 中 `active=true` 的第一筆。
- URL 變更時不觸發整頁 reload，僅 React Query refetch episode list。

### `/trajectory`

```
?episodeId=<uuid>         # 必要：指定要分析的 episode
?from=<YYYY-MM-DD>        # 可選：時間範圍下界（預設 episode startDate）
?to=<YYYY-MM-DD>          # 可選：時間範圍上界（預設 episode endDate）
?zoomStart=<YYYY-MM-DD>   # 可選：K 線圖縮放起點
?zoomEnd=<YYYY-MM-DD>     # 可選：K 線圖縮放終點
?showSMC=bos,choch,fvg,ob # 可選：逗號分隔的標記類型過濾（預設全顯示）
```

預期行為：
- 缺 `episodeId`：顯示「請從 Overview 選擇 episode」提示，附 `<Link>` 回 `/overview`。
- `from`/`to` 超出 episode 範圍：自動 clamp 到 episode 邊界。
- 縮放操作（拖拉、滾輪）會 `replaceState`（不寫入 history），避免 back 鍵體驗惡化。

### `/decision`

```
?episodeId=<uuid>&step=<int>   # 模式 A：審查歷史 episode 的某一步
?policyId=<uuid>&live=1        # 模式 B：即時推論（SSE 流）
```

預期行為：
- 兩種模式互斥；同時存在以模式 A 為準。
- 模式 B：載入時建立 SSE 連線到 `/api/v1/episodes/stream?policyId=...`。
- `step` 改變：僅 refetch trajectory frame，不重整圖表 layout。

### `/settings`

無 query params。

---

## Layout 階層

```
<AppShell>                              # 整體框架
  ├── <TopBar>                          # 上方：logo、policy switcher、user 偏好按鈕
  ├── <SideNav>                         # 左側：4 個主要頁面 link
  └── <main>
      └── <Outlet />                    # 子路由 page component
```

### `<AppShell>` 響應式行為

- ≥ 1280px（desktop）：side nav 永遠展開、寬 240px。
- 768px–1279px：side nav 收合為 icon-only（hover 展開 popover）。
- < 768px：side nav 變為 hamburger menu；圖表進入「降級可看」模式（spec FR-015：
  顯示縮圖 + 提示「請使用桌機檢視完整功能」）。

### `<TopBar>` 元素

- 左：logo + 「PPO-SMC Asset Allocation 戰情室」字樣
- 中：當前 policy 顯示與切換器
- 右：語言切換（zh-TW / en）、主題切換（亮／暗）、？icon（連到 README）

---

## 載入與錯誤狀態契約

每個頁面 component 必須處理以下三種狀態：

```typescript
// 偽碼
function OverviewPage() {
  const { data, status, error } = useEpisodeList(...);
  if (status === 'pending') return <LoadingSkeleton variant="overview" />;
  if (status === 'error')   return <ErrorBoundary error={error} retry={refetch} />;
  return <OverviewContent data={data} />;
}
```

`<LoadingSkeleton>` 必須對齊最終 layout 維度（避免 CLS > 0.1）；`<ErrorBoundary>` 必須
顯示：人話訊息（i18n）、`traceId`（可複製）、retry 按鈕（若 `retryable=true`）。

---

## 導航鍵盤無障礙性

- 整個 `<SideNav>` 必須可用 Tab 鍵聚焦，Enter／Space 觸發。
- Focus trap：modal 開啟時 Tab 不應跳出 modal。
- skip-to-content link：第一個 Tab 焦點為「跳到主內容」（i18n: `nav.skipToMain`）。
- ARIA：
  - `<TopBar>` 為 `role="banner"`
  - `<SideNav>` 為 `role="navigation"` + `aria-label="主導覽"`
  - `<main>` 為 `role="main"`

---

## 路由變更生命週期

```
URL change
  ↓
React Router matches route
  ↓
Loader（若有）prefetch（用 React Query queryClient.prefetchQuery）
  ↓
Render new page component
  ↓
On unmount：useEffect cleanup（取消 SSE、清除 chart）
```

頁面切換不應 reset React Query 全域 cache（episode list 跨頁共用）；只有「使用者切換
policy」這類顯式動作才 invalidate 對應 query keys。
