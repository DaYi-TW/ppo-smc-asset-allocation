# War Room Dashboard — Google Stitch UI Design Brief

**Feature**: 007-react-warroom
**Created**: 2026-05-04
**Purpose**: 給 Google Stitch 生成 UI mockup 用的視覺設計需求文件。本文件**只描述視覺與互動**，不含工程契約（API、microservice、testing 等請見 `spec.md` / `plan.md` / `contracts/`）。

文件分兩部分：

- **§ A — English prompt** ：可直接複製貼至 Stitch（推薦使用，Stitch 對英文理解較佳）。
- **§ B — 繁體中文設計需求** ：給人類審閱用，與 § A 內容一致。

---

# § A — English Prompt for Google Stitch

## Project Context

A web-based "War Room" dashboard for visualizing AI-driven portfolio allocation decisions. The system trains a Proximal Policy Optimization (PPO) reinforcement-learning agent on Smart Money Concepts (SMC) features (BOS / CHoCh / FVG / OB) over 8 years of multi-asset historical data. The dashboard lets researchers, paper reviewers, and risk managers replay the agent's daily allocation decisions, compare strategies, and visually verify SMC signals on candlestick charts.

This is a **professional analytics tool**, not a consumer app. Density of information matters more than friendliness. Aesthetic should feel like Bloomberg Terminal × Linear × TradingView — quantitative, dark-mode-first, monospace numbers, clean grid layouts, restrained color usage where color encodes meaning rather than decoration.

Audience: PhD-level finance + ML researchers. Locale primary: Traditional Chinese (zh-TW); secondary: English. Design must accommodate both.

## Visual Style

- **Mode**: Dark mode primary (paper presentation will use this); light mode secondary.
- **Mood**: Quant-research workstation. High information density, minimal chrome, no marketing language, no hero illustrations.
- **Type system**:
  - UI text: Inter (Latin) / Noto Sans TC (Chinese), 14–16px body, 12px labels, 24–30px headings.
  - **Numerical values use JetBrains Mono** (monospace). NAV, percentages, weights, prices — always mono so columns align.
- **Border-radius**: 8px for cards/buttons, 4px for chips/tags, 12px for modals. Avoid pill shapes.
- **Shadows**: Subtle. `0 4px 6px rgba(0,0,0,0.4)` on dark, almost invisible on light. No glow effects.
- **Spacing scale**: 4 / 8 / 12 / 16 / 24 / 32 px. Use generous whitespace inside data tables.

## Color Tokens (must match exactly)

### Dark theme (primary)
- Background base: `#0F172A`
- Card surface: `#1E293B`
- Elevated (modal): `#334155`
- Text primary: `#F1F5F9`
- Text secondary: `#CBD5E1`
- Text muted: `#64748B`
- Border default: `#334155`
- Primary action: `#3B82F6`
- Success / positive return: `#22C55E`
- Danger / negative return / drawdown: `#EF4444`
- Warning: `#FBBF24`

### Asset-specific colors (consistent across themes)
- NVDA: `#76B900` (Nvidia brand green)
- AMD: `#ED1C24` (AMD brand red)
- TSM: `#CC0000`
- MU: `#B71F31`
- GLD (Gold): `#FFD700`
- TLT (Treasury): `#1E40AF`
- Cash: `#64748B`

### SMC marker colors
- BOS bullish: green up-arrow `#22C55E`
- BOS bearish: red down-arrow `#EF4444`
- CHoCh: gold arrow `#FACC15`
- FVG zone: translucent blue rectangle `#0EA5E9` at 15% opacity
- OB demand: translucent green rectangle `#10B981` at 20% opacity
- OB supply: translucent red rectangle `#EF4444` at 20% opacity

## Layout Architecture

The app uses a **persistent shell** with three regions:

1. **Top bar (height 56px)**: Logo + product name on left ("PPO-SMC War Room"), policy switcher dropdown in center, user controls (language, theme, help) on right.
2. **Side nav (width 240px desktop, collapsed to 56px icon-only on tablet)**: Four navigation items, each with icon + label.
3. **Main content (fluid)**: Page-specific content with consistent 24px padding.

Below 768px width, side nav becomes a hamburger menu. The dashboard is desktop-first; mobile is read-only.

## Pages

Generate four primary pages plus a 404 page. Each page must show realistic placeholder data for an 8-year backtest of an AI allocation agent over the assets NVDA, AMD, TSM, MU, GLD, TLT, plus a Cash bucket.

### Page 1: Overview (`/overview`)

**Purpose**: Landing page. Shows a list of historical episodes (backtest runs) with key metrics, plus quick performance summary cards.

**Layout**:

- **Top section (4 KPI cards in a row)**:
  1. "Final NAV" — large mono number `116.79x`, with trend sparkline below.
  2. "CAGR" — `+77.5%`, success-green color.
  3. "Max Drawdown" — `−16.2%`, danger-red color.
  4. "Sharpe Ratio" — `2.54`, neutral.
- **Middle section (full-width chart card, ~400px tall)**:
  - Title: "Cumulative NAV — All Strategies"
  - Multi-line chart comparing 3 strategies: "PPO + SMC" (primary blue line, thick), "PPO no-SMC" (dashed gray, "Pending ablation" tag), "NVDA Buy & Hold" (orange, dotted).
  - X-axis: 2018-01 to 2026-04, monthly tick labels.
  - Y-axis: log scale toggle in top-right.
  - Hover crosshair shows date + NAV per strategy in a floating dark tooltip.
- **Bottom section (data table card)**:
  - Title: "Recent Episodes"
  - Columns: Episode ID (truncated UUID), Policy, Date Range, Final NAV (mono, right-aligned), CAGR (color-coded), Max DD (red), Sharpe (mono), Status (chip: "Completed" green / "Running" blue with spinner / "Failed" red).
  - 8 rows of placeholder data.
  - Each row clickable, hover shows subtle highlight.

### Page 2: Trajectory Analysis (`/trajectory`)

**Purpose**: Deep-dive into a single episode. Three tabs: **Weights**, **Risk**, **SMC View**.

**Layout (top-level shared)**:

- **Episode header card (always visible)**:
  - Left: Episode ID + Policy name + Date range.
  - Right: 4 mini-stats inline (Final NAV, CAGR, Max DD, Sharpe). Mono numbers.
- **Tab bar** below header: Weights | Risk | SMC View.
- **Time-range brush** (always visible at bottom of content, ~80px tall): Mini area chart with two draggable handles for zoom selection. Shows full episode range.

**Tab A — Weights**:

- **Stacked area chart** filling main content area (~600px tall):
  - X-axis: dates (2018-01 to 2026-04).
  - Y-axis: 0 to 100% allocation.
  - Layers stacked bottom-to-top: Cash (gray) → TLT (deep blue) → GLD (gold) → MU (red) → TSM (red) → AMD (red) → NVDA (green). Layer labels float on right edge.
  - Hover crosshair shows a vertical line and a tooltip listing all 7 weights with mono percentages summing to 100%.
  - Legend chips above chart, clickable to toggle layers.
- **Right side panel (320px wide)**: "At Selected Date" — pinned date display, large 7-bar horizontal bar chart of current weights, and a small reward-decomposition mini-chart (3 bars: log return, drawdown penalty, turnover penalty).

**Tab B — Risk**:

- **Top chart (NAV)**: Single line chart, log-scale toggle in top-right. Annotations on key dates: "COVID 2020-03", "Fed Pivot 2022-Q4", "AI Bull Start 2023-01". Annotations are vertical dashed lines with label boxes above.
- **Bottom chart (Drawdown)**: Filled red area chart from 0 to negative values, shares X-axis with NAV chart. Max-drawdown point marked with a small circle and label `−16.2%`.
- **Crosshair synced across both charts** — moving mouse on NAV updates a vertical line on Drawdown.
- **Right panel (320px)**: Risk metrics card stack — "VaR 95%", "30-day Volatility", "Sortino Ratio", "Calmar Ratio" — each as a label + large mono value.

**Tab C — SMC View**:

- **Asset selector** (top): Pill toggle group for NVDA / AMD / TSM / MU / GLD / TLT. Selected pill has filled background.
- **Time-range buttons**: "30d" / "90d" / "1y" / "All" pill toggle.
- **Candlestick chart** (~500px tall) with green/red OHLC bars, plus overlays:
  - BOS bullish marks: small green ▲ above price + label "BOS".
  - BOS bearish marks: red ▼ below price + label "BOS".
  - CHoCh marks: gold ◆ + label "CHoCh".
  - FVG zones: light-blue translucent rectangles spanning a date range and price band, with thin border.
  - OB zones: green (demand) or red (supply) translucent rectangles.
- **Toggle row above chart**: 4 checkbox chips — "BOS" "CHoCh" "FVG" "OB" — each with the matching color dot. Clicking hides/shows that overlay layer.
- **Click on any marker** opens a side panel (slides in from right, 360px) showing: marker type, exact date(s), price level, detection rule (e.g. "3-bar gap, threshold 0.5%"), and "View source code" link.

### Page 3: Decision Panel (`/decision`)

**Purpose**: Inspect a single AI decision at a single timestep. Shows what the agent saw, what it chose, and why (in terms of reward components).

**Layout** (3-column grid on desktop):

- **Column 1 — Observation Input (320px)**:
  - Title: "Observation"
  - Toggle at top: "Historical step" vs "Live SSE feed".
  - If historical: date picker + step number input.
  - If live: connection status indicator (green dot "Connected" / red dot "Reconnecting...").
  - Below: a scrollable read-only panel showing the 63-dim observation vector grouped semantically — "Price momentum (6 assets × 5 features)", "Volatility (6 assets × 3)", "SMC signals (6 assets × 5)", "Current weights (7)", "Cash bucket". Each group collapsible. Numbers in mono font.

- **Column 2 — Action Output (480px, central)**:
  - Title: "Action: Allocation Vector"
  - Large horizontal bar chart with 7 rows: NVDA, AMD, TSM, MU, GLD, TLT, Cash. Each bar uses asset color, with mono percentage label at end of bar (e.g. `38.42%`).
  - Below the chart: 3-stat row — "Sum: 1.0000" (verification), "Top weight: NVDA 38.4%", "Entropy: 1.234".
  - Below that: a "Reward Breakdown" stacked horizontal bar — green segment for `log_return`, red segment for `−drawdown_penalty`, orange segment for `−turnover_penalty`. Mono numbers above each segment.

- **Column 3 — Policy Context (320px)**:
  - Title: "Policy"
  - Card showing: policy display name "PPO-SMC v1.2", git commit hash (mono, truncated), trained timestamp, training data range, final mean episode return at training. Small "Switch policy" link.
  - Below: "Recent inferences" mini-list — 5 most recent decisions with timestamp + top weight asset + total reward.

### Page 4: Settings (`/settings`)

**Purpose**: User preferences. Simple form layout in a single 640px-wide card.

**Sections**:
- Language: radio group, "繁體中文" / "English".
- Theme: 3-button toggle, "Light" / "Dark" / "System".
- Default policy: dropdown of available policies.
- Number formatting: "1,234.56" / "1.234,56".
- Timezone: "UTC" / "Local".
- Color-blind palette: "Off" / "Deuteranopia" / "Protanopia".
- Save button (primary blue) + Reset button (text-only).

### 404 Page

- Centered, vertically: large `404` in mono, "Page not found" subtitle, link "Back to overview".
- No illustration.

## Component Library Notes

- **Buttons**:
  - Primary: solid blue `#3B82F6` background, white text, 8px radius, 40px height, 16px horizontal padding.
  - Secondary: transparent background, 1px border `#334155`, text primary color.
  - Ghost: no background, no border, hover shows subtle bg `#1E293B`.
  - Danger: solid red, used only for destructive actions.
- **Inputs**: 40px height, 8px radius, dark surface `#1E293B`, focus ring 2px `#3B82F6`.
- **Chips/Tags**: 24px height, 4px radius, 12px font, padding 4px 8px. Status chips use semantic colors with 15% opacity background + solid colored text.
- **Tooltips**: dark surface `#334155`, 4px radius, 12px font, max-width 320px, arrow indicator.
- **Skeletons**: animated pulse on `#1E293B`, used for loading states; must match final layout dimensions to prevent layout shift.
- **Empty states**: centered, simple line-art icon (no full illustrations), short heading, brief description, single CTA button.

## Interaction Patterns

- **Charts**: All interactive charts have crosshair on hover, brush selection at bottom, legend toggle.
- **Tables**: Sortable columns (click header), hover row highlight, no zebra stripes.
- **Modals**: 12px radius, max-width 640px, dark backdrop with 60% opacity, ESC key closes.
- **Navigation**: Active nav item has 2px left accent bar in primary blue + filled icon. Inactive items use outline icon + muted text.
- **Loading**: Skeleton screens, not spinners (except inline within buttons or live-feed indicators).
- **Number formatting**: Mono font everywhere. Percentages 2 decimal places. NAV 4 decimal places. Prices 2 decimal places. Negative numbers prefixed with `−` (en-dash, not hyphen).

## Accessibility

- WCAG AA contrast on all text and UI elements.
- All interactive elements keyboard-navigable; visible focus rings (2px primary blue).
- Charts use **shape + color** dual encoding (▲▼ for direction, not color alone).
- Color-blind palette toggle replaces red/green with blue/orange variants.

## Output Expectations

For each of the four primary pages, produce:
- Desktop layout (1440px width).
- Tablet layout (768–1279px).
- Mobile layout (≤ 767px, read-only / degraded).
- Both dark and light theme variants.

Components shown should reflect realistic 8-year backtest data (final NAV around 100×, drawdowns 10–20%, allocation shifts visibly during 2020-03 COVID and 2022 Fed pivot dates).

---

# § B — 繁體中文設計需求（人類審閱用）

## 專案脈絡

戰情室是一套網頁式 AI 決策視覺化儀表板，呈現 PPO 強化學習代理人於 8 年（2018–2026）多資產歷史資料上之每日配置決策。核心使用者為 ML 研究者、論文審查者、口試評委、風控人員。系統以 Smart Money Concepts（BOS / CHoCh / FVG / OB）作為 RL 觀測空間之一部分，戰情室需在 K 線圖上肉眼可驗證這些訊號。

這是專業分析工具，不是消費者 app。資訊密度優先於易用度。視覺氛圍：Bloomberg Terminal × Linear × TradingView — 量化、暗色為主、數值用等寬字、grid 布局乾淨、顏色用於編碼意義而非裝飾。

## 視覺風格

- **預設模式**：暗色（論文展示優先），亮色為次要。
- **氛圍**：量化研究工作站。高資訊密度、最少 chrome、無行銷文案、無 hero 插圖。
- **字型系統**：
  - UI 文字：Inter（拉丁字）／Noto Sans TC（中文）；body 14–16px、label 12px、heading 24–30px。
  - **數值（NAV、百分比、權重、價格）一律用 JetBrains Mono 等寬字**，確保欄位對齊。
- **圓角**：卡片／按鈕 8px、chip／tag 4px、modal 12px。**不用** pill 形狀。
- **陰影**：低調。暗色用 `0 4px 6px rgba(0,0,0,0.4)`，亮色幾乎不可見。無 glow 效果。
- **間距尺度**：4 / 8 / 12 / 16 / 24 / 32 px。資料表內留白要充裕。

## 色彩 Token

### 暗色主題（主要）

| 角色 | Hex |
|------|-----|
| 背景底色 | `#0F172A` |
| 卡片表面 | `#1E293B` |
| 浮層（modal） | `#334155` |
| 主要文字 | `#F1F5F9` |
| 次要文字 | `#CBD5E1` |
| 提示文字 | `#64748B` |
| 邊線 | `#334155` |
| 主操作 | `#3B82F6` |
| 正報酬／成功 | `#22C55E` |
| 負報酬／回撤／危險 | `#EF4444` |
| 警告 | `#FBBF24` |

### 資產專用色（亮暗主題一致）

| 資產 | 顏色 | 含義 |
|------|------|------|
| NVDA | `#76B900` | Nvidia 品牌綠 |
| AMD | `#ED1C24` | AMD 品牌紅 |
| TSM | `#CC0000` | TSMC 品牌紅 |
| MU | `#B71F31` | Micron 品牌紅 |
| GLD | `#FFD700` | 金色 |
| TLT | `#1E40AF` | 深藍（債券） |
| Cash | `#64748B` | 中性灰 |

### SMC 標記色

| 標記 | 視覺 |
|------|------|
| BOS 看漲 | 綠色向上箭頭（▲）`#22C55E` |
| BOS 看跌 | 紅色向下箭頭（▼）`#EF4444` |
| CHoCh | 金色箭頭 `#FACC15` |
| FVG 區塊 | 半透明藍色矩形 `#0EA5E9` 15% opacity |
| OB demand | 半透明綠色矩形 `#10B981` 20% opacity |
| OB supply | 半透明紅色矩形 `#EF4444` 20% opacity |

## 整體 Layout 架構

三區塊持久外殼：

1. **頂列（高 56px）**：左側 logo + 產品名（"PPO-SMC War Room"）、中間 policy 切換 dropdown、右側使用者控制（語言、主題、說明）。
2. **左側 nav（桌機寬 240px、平板收合為 56px icon-only）**：四個導覽項目，圖示 + 文字。
3. **主內容區（流動）**：頁面內容，padding 24px。

寬度 < 768px 時側 nav 改為 hamburger。整體桌機優先，行動裝置降級唯讀。

## 四個主要頁面

每個頁面都應顯示**8 年回測**之合理 placeholder 數據（資產：NVDA/AMD/TSM/MU/GLD/TLT + Cash）。

### 頁面 1：Overview `/overview`

著陸頁。顯示歷史 episode 列表 + 績效摘要卡。

**Layout**：

- **頂部 4 張 KPI 卡（一列）**：
  1. **Final NAV** — 大號 mono 數字 `116.79x`，下方迷你 sparkline。
  2. **CAGR** — `+77.5%`，綠色。
  3. **最大回撤** — `−16.2%`，紅色。
  4. **Sharpe Ratio** — `2.54`，中性。
- **中段 全寬圖表卡（高 ~400px）**：
  - 標題：「Cumulative NAV — All Strategies」
  - 多線比對 3 策略：「PPO + SMC」（主線粗藍）、「PPO no-SMC」（虛線灰，附「Pending ablation」標籤）、「NVDA Buy & Hold」（橘色點線）。
  - X 軸：2018-01 至 2026-04，月度刻度。
  - Y 軸：右上有 log scale 切換按鈕。
  - Hover 顯示 crosshair + 浮動 tooltip 列出三策略當日 NAV。
- **下段 資料表卡**：
  - 標題：「Recent Episodes」
  - 欄位：Episode ID、Policy、Date Range、Final NAV、CAGR、Max DD、Sharpe、Status。
  - 數值欄右對齊、mono 字。Status 用 chip 配色。
  - 8 列 placeholder。整列可點擊。

### 頁面 2：Trajectory Analysis `/trajectory`

單一 episode 深入分析，含三個 tab：**Weights** / **Risk** / **SMC View**。

**共用區塊**：

- **Episode header card**（永遠可見）：左 episode ID + policy 名稱 + 日期範圍；右 4 個 inline mini-stats（Final NAV、CAGR、Max DD、Sharpe）。
- **Tab bar**：Weights | Risk | SMC View。
- **時間範圍 brush**（內容區下方，高 ~80px）：迷你 area chart，兩個可拖拉手把選範圍。

**Tab A — Weights**：

- **Stacked area chart**（填滿主區，高 ~600px）：
  - X 軸日期、Y 軸 0–100% 配置。
  - 由下往上堆疊：Cash（灰）→ TLT（深藍）→ GLD（金）→ MU（紅）→ TSM（紅）→ AMD（紅）→ NVDA（綠）。
  - Hover 顯示 crosshair + tooltip 列出 7 個權重（mono 百分比，sum = 100%）。
  - Legend chip 在圖表上方，可點擊切換層顯示。
- **右側面板（寬 320px）**：「At Selected Date」— 顯示選定日期、7-bar 水平 bar chart、reward 三項分量小圖（log_return、drawdown_penalty、turnover_penalty）。

**Tab B — Risk**：

- **上方 NAV 圖**：單線 line chart，右上 log scale 切換。在關鍵日期加垂直虛線 + 標籤盒：「COVID 2020-03」「Fed Pivot 2022-Q4」「AI Bull 2023-01」。
- **下方 Drawdown 圖**：紅色填充 area chart（從 0 到負值），與 NAV 圖共用 X 軸。最大回撤點標小圓圈 + 標籤 `−16.2%`。
- **十字游標跨兩圖同步**。
- **右側面板（320px）**：風險指標卡疊 — VaR 95%、30 日波動度、Sortino、Calmar，皆 label + 大 mono 值。

**Tab C — SMC View**：

- **資產選擇器**（最上）：6 個 pill（NVDA/AMD/TSM/MU/GLD/TLT），選中者填底色。
- **時間範圍按鈕**：「30d」「90d」「1y」「All」pill。
- **K 線圖**（高 ~500px）：綠紅 OHLC bar + 標記層：
  - BOS 看漲：價格上方小綠 ▲ + 標籤「BOS」
  - BOS 看跌：價格下方紅 ▼ + 標籤「BOS」
  - CHoCh：金色 ◆ + 標籤
  - FVG：半透明藍色矩形跨日期範圍 × 價格區段，細邊框
  - OB：綠（demand）／紅（supply）半透明矩形
- **圖表上方 toggle 列**：4 個 checkbox chip（BOS / CHoCh / FVG / OB），各帶對應色點，可隱藏該層。
- **點擊任一標記**：右側滑入 panel（寬 360px），顯示標記類型、日期、價格、判定規則（如「3 根 K 棒缺口、門檻 0.5%」）、「View source code」連結。

### 頁面 3：Decision Panel `/decision`

檢視單一 AI 決策：agent 看到什麼、選了什麼、為什麼（reward 分解）。

**Layout**（桌機 3 欄）：

- **欄 1 — Observation Input（320px）**：
  - 頂部 toggle：「Historical step」vs「Live SSE feed」
  - Historical：日期 picker + step 編號輸入
  - Live：連線狀態 indicator（綠點 Connected / 紅點 Reconnecting...）
  - 下方：唯讀 panel 顯示 63 維 observation 向量，按語意分組 — 「Price momentum (6 assets × 5)」「Volatility (6 × 3)」「SMC signals (6 × 5)」「Current weights (7)」「Cash bucket」。每組可摺疊。數值 mono 字。

- **欄 2 — Action Output（480px，中央）**：
  - 標題：「Action: Allocation Vector」
  - 大型水平 bar chart 7 列（NVDA/AMD/TSM/MU/GLD/TLT/Cash），各 bar 用資產色，bar 末端 mono 百分比（如 `38.42%`）。
  - 圖下 3-stat 行：「Sum: 1.0000」「Top weight: NVDA 38.4%」「Entropy: 1.234」。
  - 再下方：「Reward Breakdown」堆疊水平 bar — 綠色段 `log_return`、紅色段 `−drawdown_penalty`、橘色段 `−turnover_penalty`。各段上方 mono 數字。

- **欄 3 — Policy Context（320px）**：
  - 標題：「Policy」
  - 卡片顯示：policy 名稱「PPO-SMC v1.2」、git commit hash（mono，截斷顯示）、訓練時間、訓練資料區間、final mean episode return。小型「Switch policy」連結。
  - 下方「Recent inferences」迷你列表 — 5 筆近期決策，含時間戳 + 最大權重資產 + 總 reward。

### 頁面 4：Settings `/settings`

簡單表單 layout，640px 寬卡片：

- 語言：radio group（繁體中文／English）
- 主題：3 按鈕 toggle（Light / Dark / System）
- 預設 policy：dropdown
- 數字格式：「1,234.56」/「1.234,56」
- 時區：UTC / Local
- 色盲調色盤：Off / Deuteranopia / Protanopia
- Save 按鈕（主藍）+ Reset 文字按鈕

### 404 頁

水平垂直置中：大號 mono `404`、「Page not found」副標、「Back to overview」連結。無插圖。

## 元件規格

- **按鈕**：
  - Primary：實心藍 `#3B82F6` 底、白字、8px 圓角、高 40px、左右 padding 16px。
  - Secondary：透明底、1px 邊線 `#334155`、主文字色。
  - Ghost：無底無邊、hover 顯示淺底 `#1E293B`。
  - Danger：實心紅，僅用於破壞性操作。
- **Input**：高 40px、8px 圓角、暗色表面 `#1E293B`、focus ring 2px `#3B82F6`。
- **Chip / Tag**：高 24px、4px 圓角、12px 字、padding 4px 8px。Status chip 用語意色 15% opacity 底 + 實心字色。
- **Tooltip**：暗底 `#334155`、4px 圓角、12px 字、max-width 320px、有箭頭。
- **Skeleton**：在 `#1E293B` 上脈動動畫，loading 狀態用，需與最終 layout 對齊以免 layout shift。
- **Empty state**：置中、簡單線稿 icon（不要完整插圖）、短標題、簡短說明、單一 CTA。

## 互動模式

- **圖表**：所有互動圖表皆有 hover crosshair、底部 brush 選取、legend toggle。
- **表格**：欄位可排序（點 header）、hover 列高亮、不要斑馬紋。
- **Modal**：12px 圓角、max-width 640px、暗 backdrop 60% opacity、ESC 關閉。
- **導覽**：active nav 項目有 2px 主藍左側 accent bar + 實心 icon。Inactive 用外框 icon + muted 字色。
- **載入**：用 skeleton screen，不用 spinner（按鈕內或 live-feed indicator 例外）。
- **數字格式**：永遠 mono 字。百分比 2 位小數。NAV 4 位小數。價格 2 位小數。負號用 en-dash `−`，不用 hyphen `-`。

## 無障礙

- 所有文字與 UI 元件 WCAG AA 對比度。
- 所有互動元件可鍵盤操作；可見 focus ring（2px 主藍）。
- 圖表用**形狀 + 顏色雙重編碼**（▲▼ 表方向，不僅靠紅綠）。
- 色盲調色盤切換以藍／橘變體取代紅／綠。

## 輸出期望

每個主要頁面生成：

- 桌機（1440px 寬）
- 平板（768–1279px）
- 行動（≤ 767px，唯讀降級）
- 暗色與亮色雙主題

placeholder 資料應反映 8 年回測之合理數值（Final NAV ~100×、回撤 10–20%、2020-03 COVID 與 2022 Fed pivot 期間配置明顯切換）。

---

## 使用方式

1. 開啟 [Google Stitch](https://stitch.withgoogle.com)。
2. 複製 § A 整段（從 "Project Context" 到 "Output Expectations" 結尾）。
3. 貼到 Stitch prompt 框。
4. 若一次塞不下，可分頁面跑：先貼「Project Context + Visual Style + Color Tokens + Layout Architecture」，再分別跑每個 Page 1/2/3/4。
5. Stitch 輸出 mockup 後，可選擇 export to React + Tailwind code，或匯出 Figma 檔。

## 與工程契約的關係

本文件**僅描述視覺與互動**。資料模型、API 端點、microservice 通訊、testing 規範等請見：

- `spec.md` — 完整功能需求（FR-001 至 FR-031）
- `plan.md` — 實作計畫
- `data-model.md` — TypeScript ViewModel 定義
- `contracts/api-mapping.md` — 006 Gateway endpoint 對應
- `contracts/theme-tokens.md` — 完整 design token（亮暗主題、Tailwind preset）
- `contracts/ui-routes.md` — 路由與 layout 詳細規格
- `contracts/i18n-keys.md` — i18n key 命名規約
