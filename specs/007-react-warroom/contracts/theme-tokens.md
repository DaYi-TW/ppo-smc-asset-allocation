# Theme Tokens Contract

**Feature**: 007-react-warroom
**Date**: 2026-04-29

定義戰情室前端的設計 token、亮／暗主題切換規約，以及 Tailwind preset 的擴充規則。

---

## Token 命名規範

採三層命名：`<category>-<role>-<state>`
- category：color | spacing | radius | font | shadow | z-index
- role：primary | secondary | success | danger | warn | info | surface | text
- state：default | hover | active | disabled

範例：`color-primary-default`、`color-text-secondary`。

---

## 顏色 Token

### 亮色（light theme，root: `:root`）

| Token                     | Hex       | 用途                                  |
|---------------------------|-----------|---------------------------------------|
| `--color-bg-base`         | `#FFFFFF` | 整體背景                              |
| `--color-bg-surface`      | `#F8FAFC` | 卡片、面板背景                        |
| `--color-bg-elevated`     | `#FFFFFF` | popover、modal                        |
| `--color-text-primary`    | `#0F172A` | 主要文字                              |
| `--color-text-secondary`  | `#475569` | 次要文字（標籤、說明）                |
| `--color-text-muted`      | `#94A3B8` | 提示／停用文字                        |
| `--color-border-default`  | `#E2E8F0` | 一般邊線                              |
| `--color-border-strong`   | `#CBD5E1` | 強調邊線（focused input）             |
| `--color-primary-default` | `#2563EB` | 主操作按鈕、連結                      |
| `--color-primary-hover`   | `#1D4ED8` |                                       |
| `--color-success`         | `#16A34A` | 漲幅、正報酬、BOS_BULL 箭頭           |
| `--color-danger`          | `#DC2626` | 跌幅、負報酬、drawdown、BOS_BEAR 箭頭 |
| `--color-warn`            | `#F59E0B` | warning、quality_flag != 'ok'         |
| `--color-info`            | `#0EA5E9` | info banner、FVG 矩形                 |
| `--color-choch`           | `#EAB308` | CHoCh 箭頭（金色）                    |
| `--color-ob-demand`       | `#10B981` | OB demand zone（綠色）                |
| `--color-ob-supply`       | `#EF4444` | OB supply zone（紅色）                |
| `--color-cash`            | `#64748B` | Cash 權重區塊                         |

### 暗色（dark theme，root: `.dark`）

| Token                     | Hex       |
|---------------------------|-----------|
| `--color-bg-base`         | `#0F172A` |
| `--color-bg-surface`      | `#1E293B` |
| `--color-bg-elevated`     | `#334155` |
| `--color-text-primary`    | `#F1F5F9` |
| `--color-text-secondary`  | `#CBD5E1` |
| `--color-text-muted`      | `#64748B` |
| `--color-border-default`  | `#334155` |
| `--color-border-strong`   | `#475569` |
| `--color-primary-default` | `#3B82F6` |
| `--color-primary-hover`   | `#2563EB` |
| `--color-success`         | `#22C55E` |
| `--color-danger`          | `#EF4444` |
| `--color-warn`            | `#FBBF24` |
| `--color-info`            | `#38BDF8` |
| `--color-choch`           | `#FACC15` |
| `--color-ob-demand`       | `#34D399` |
| `--color-ob-supply`       | `#F87171` |
| `--color-cash`            | `#94A3B8` |

### 圖表專用 palette（不隨主題變色，以保證亮暗一致辨識）

| Asset / Series       | Color     | 註解                          |
|----------------------|-----------|-------------------------------|
| NVDA                 | `#76B900` | NVIDIA 品牌綠                 |
| AMD                  | `#ED1C24` | AMD 品牌紅                    |
| TSM                  | `#CC0000` | TSMC 品牌紅                   |
| MU                   | `#B71F31` | Micron 品牌紅                 |
| GLD                  | `#FFD700` | 金色（明顯區隔）              |
| TLT                  | `#1E40AF` | 深藍（債券）                  |
| Cash                 | `#64748B` | 中性灰                        |
| NAV line             | `#0F172A` (light) / `#F1F5F9` (dark) | |
| Drawdown line        | `#DC2626` | 永遠紅色，與 NAV 對比         |

對色盲友善：紅／綠對比使用 + 形狀（▲▼）雙重編碼，不僅靠顏色。

---

## 間距 Token（Tailwind 對應）

| Token            | Value    | Tailwind class |
|------------------|----------|----------------|
| `--space-xs`     | `4px`    | `p-1`          |
| `--space-sm`     | `8px`    | `p-2`          |
| `--space-md`     | `12px`   | `p-3`          |
| `--space-lg`     | `16px`   | `p-4`          |
| `--space-xl`     | `24px`   | `p-6`          |
| `--space-2xl`    | `32px`   | `p-8`          |

---

## 字型 Token

| Token                 | Value                                                |
|-----------------------|------------------------------------------------------|
| `--font-family-sans`  | `'Inter', 'Noto Sans TC', system-ui, sans-serif`     |
| `--font-family-mono`  | `'JetBrains Mono', 'Consolas', monospace`            |
| `--font-size-xs`      | `0.75rem` (12px)                                     |
| `--font-size-sm`      | `0.875rem` (14px)                                    |
| `--font-size-base`    | `1rem` (16px)                                        |
| `--font-size-lg`      | `1.125rem` (18px)                                    |
| `--font-size-xl`      | `1.25rem` (20px)                                     |
| `--font-size-2xl`     | `1.5rem` (24px)                                      |
| `--font-size-3xl`     | `1.875rem` (30px)                                    |

數值（金額、百分比）一律用 mono font，避免不同字寬造成對齊偏移。

---

## 圓角／陰影／z-index

| Token              | Value       | 用途                |
|--------------------|-------------|---------------------|
| `--radius-sm`      | `4px`       | 小型 chip、tag      |
| `--radius-md`      | `8px`       | 卡片、按鈕          |
| `--radius-lg`      | `12px`      | 大型卡片            |
| `--shadow-sm`      | `0 1px 2px rgba(0,0,0,0.05)` | hover state |
| `--shadow-md`      | `0 4px 6px rgba(0,0,0,0.07)` | dropdown    |
| `--shadow-lg`      | `0 10px 15px rgba(0,0,0,0.1)` | modal      |
| `--z-base`         | `0`         | 基礎內容            |
| `--z-overlay`      | `40`        | sticky header       |
| `--z-modal`        | `50`        | dialog              |
| `--z-tooltip`      | `60`        | tooltip／popover    |

暗色模式陰影 alpha 提高至 0.4（`rgba(0,0,0,0.4)`）以維持可見度。

---

## 主題切換邏輯

`<html>` 元素加入 class：
- 亮色：無 class
- 暗色：`class="dark"`
- 系統：依 `window.matchMedia('(prefers-color-scheme: dark)').matches`

切換實作：

```typescript
// src/theme/applyTheme.ts
export function applyTheme(theme: 'light' | 'dark' | 'system') {
  const root = document.documentElement;
  if (theme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.toggle('dark', isDark);
  } else {
    root.classList.toggle('dark', theme === 'dark');
  }
}
```

監聽系統變更（system 模式才需）：

```typescript
const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener('change', () => applyTheme('system'));
```

---

## Tailwind Preset 結構

```typescript
// src/theme/tailwind-preset.ts
import type { Config } from 'tailwindcss';

const preset: Partial<Config> = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: 'var(--color-primary-default)', hover: 'var(--color-primary-hover)' },
        success: 'var(--color-success)',
        danger: 'var(--color-danger)',
        // ... 對應上方所有 color token
      },
      fontFamily: {
        sans: 'var(--font-family-sans)',
        mono: 'var(--font-family-mono)',
      },
    },
  },
};
export default preset;
```

`apps/warroom/tailwind.config.ts` 只需 `presets: [preset]` + `content: [...paths]`。

---

## 圖表元件主題注入

Recharts 與 lightweight-charts 不支援 CSS variables，必須在 runtime 讀取：

```typescript
// src/theme/getChartTheme.ts
export function getChartTheme(): ChartTheme {
  const styles = getComputedStyle(document.documentElement);
  return {
    background: styles.getPropertyValue('--color-bg-surface').trim(),
    text: styles.getPropertyValue('--color-text-primary').trim(),
    grid: styles.getPropertyValue('--color-border-default').trim(),
    success: styles.getPropertyValue('--color-success').trim(),
    danger: styles.getPropertyValue('--color-danger').trim(),
    // ...
  };
}
```

主題切換時，圖表 component 需 useEffect 重新讀 theme 並觸發 chart re-render。

---

## Accessibility 對比要求

依 WCAG AA：
- 一般文字（< 18pt）：對比 ≥ 4.5:1
- 大型文字（≥ 18pt）：對比 ≥ 3:1
- UI 元件邊線：對比 ≥ 3:1

亮／暗主題上方所有 token 已預先驗證對比（透過 `pa11y-ci` 在 CI 跑）。新增 token 時需重跑
驗證。
