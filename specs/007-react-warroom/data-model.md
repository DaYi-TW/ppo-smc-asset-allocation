# Phase 1 Data Model: 戰情室前端 View Model

**Feature**: 007-react-warroom
**Date**: 2026-04-29

本文件定義前端 TypeScript view model（位於 `src/viewmodels/`），以及與 006 Spring Gateway
API DTO 的轉換契約。所有 TypeScript 介面均使用 `strict: true` 規範撰寫。

---

## 1. 命名與型別約定

- **API DTO**：006 Gateway 已將 envelope 統一為 camelCase，前端不再做 case 轉換。
- **ViewModel**：以 `XxxViewModel` 結尾，純前端用，可能含計算欄位（如 `drawdownPct`）。
- **錯誤類型**：使用 `discriminated union` 表示 loading / error / success state；React Query
  的 `status` 已涵蓋此模式。
- **時間**：API 傳 ISO 8601 字串，ViewModel 保留為 `string`，僅在 chart 元件內 lazy 轉
  `Date`／epoch ms（避免序列化成本）。
- **金額**：number（USD），格式化為千分位逗號 + 2 位小數 + `$` 前綴。
- **百分比**：number（0-1 範圍），格式化為 2 位小數 + `%`。

---

## 2. Episode 相關

### 2.1 EpisodeSummaryViewModel

對應 GET `/api/v1/episodes` 回應陣列元素。

```typescript
interface EpisodeSummaryViewModel {
  episodeId: string;          // UUID
  policyId: string;           // 對應 PolicyMetadata.id
  policyVersion: string;      // semver
  startDate: string;          // ISO 8601 date (YYYY-MM-DD)
  endDate: string;
  totalReturn: number;        // 0.123 = +12.3%
  maxDrawdown: number;        // 0.085 = -8.5%（保存為正數，UI 顯示加負號）
  sharpeRatio: number;
  totalSteps: number;
  status: EpisodeStatus;
  createdAt: string;          // ISO 8601 datetime
}

type EpisodeStatus = 'pending' | 'running' | 'completed' | 'failed';
```

**Invariant**：`completed` 必有 `totalReturn`、`maxDrawdown`、`sharpeRatio`；其餘狀態這三
個欄位可能為 0。前端應以 `status === 'completed'` 為渲染前提。

### 2.2 EpisodeDetailViewModel

對應 GET `/api/v1/episodes/{id}`。

```typescript
interface EpisodeDetailViewModel extends EpisodeSummaryViewModel {
  config: EpisodeConfig;            // 訓練／推論時用的設定
  trajectoryUri?: string;           // S3 URI（若 size > 1 MB）
  trajectoryInline?: TrajectoryFrame[];  // 若 size <= 1 MB 直接內嵌
  rewardBreakdown: RewardSeries;    // 全程 reward 分解（aligned to trajectory）
  errorMessage?: string;            // 僅 status='failed' 時存在
}

interface EpisodeConfig {
  initialNav: number;          // 初始淨值（USD）
  symbols: string[];           // 例：['NVDA', 'AMD', 'TSM', 'GLD', 'TLT']
  rebalanceFrequency: 'daily' | 'weekly';
  transactionCostBps: number;  // basis points（10 = 0.1%）
  slippageBps: number;
  riskFreeRate: number;        // 年化 0.045 = 4.5%
}
```

**Invariant**：`trajectoryUri` 與 `trajectoryInline` 互斥（XOR），對齊 006 db schema 的
`chk_trajectory_xor`。

---

## 3. Trajectory（時間序列）

### 3.1 TrajectoryFrame

對應 trajectory parquet（或 inline JSON）的單筆資料；前端載入後轉成 array of frame。

```typescript
interface TrajectoryFrame {
  timestamp: string;          // ISO 8601 date
  step: number;               // 0-based
  weights: WeightAllocation;  // 權重（合計必為 1.0）
  nav: number;                // 該日結算淨值
  drawdownPct: number;        // 0-1，從 peak 算起
  reward: RewardSnapshot;     // 該步 reward 三元件
  smcSignals: SMCSignals;     // 該日 SMC 觀測
  ohlcv: OHLCV;               // 主資產（NVDA）的當日 K 線；其他資產從 episode config 衍生
  action: ActionVector;       // policy 輸出
}

interface WeightAllocation {
  riskOn: number;     // NVDA + AMD + TSM 合計（顯示用聚合）
  riskOff: number;    // GLD + TLT 合計
  cash: number;
  // 細項（hover 顯示）
  perAsset: Record<string, number>;  // { NVDA: 0.25, AMD: 0.15, ... }
}

interface RewardSnapshot {
  total: number;              // = returnComponent - drawdownPenalty - costPenalty
  returnComponent: number;
  drawdownPenalty: number;    // 正值表示扣分量（公式上是 -|...|，前端顯示時加負號）
  costPenalty: number;
}

interface OHLCV {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface ActionVector {
  raw: number[];             // policy 原始輸出
  normalized: number[];      // softmax 後
  logProb: number;           // 該動作的 log-probability
  entropy: number;           // 該步 policy entropy（觀察探索度用）
}
```

**Invariant**：
- `Math.abs(weights.riskOn + weights.riskOff + weights.cash - 1.0) < 1e-6`
- `Object.values(weights.perAsset).reduce((a,b)=>a+b, 0) ≈ weights.riskOn + weights.riskOff`
- `reward.total === reward.returnComponent - reward.drawdownPenalty - reward.costPenalty`
  （容許 1e-9 浮點誤差）

---

## 4. SMC 標記

### 4.1 SMCSignals（單個時間點觀測）

```typescript
interface SMCSignals {
  bos: -1 | 0 | 1;            // -1 看跌結構破壞、0 無、1 看漲結構破壞
  choch: -1 | 0 | 1;          // 同上但為 Change of Character
  fvgDistancePct: number;     // 至最近 unfilled FVG 的距離（價格比例）；若無 FVG = NaN
  obTouching: boolean;        // 當下價格是否接觸 active Order Block
  obDistanceRatio: number;    // 至最近 OB 的距離 / ATR；若無 OB = NaN
}
```

### 4.2 SMCMarker（K 線圖疊加用聚合資料）

從整個 trajectory 萃取出的可繪製事件：

```typescript
type SMCMarkerKind = 'BOS_BULL' | 'BOS_BEAR' | 'CHOCH_BULL' | 'CHOCH_BEAR' | 'FVG' | 'OB';

interface SMCMarker {
  id: string;                    // 穩定 key（用於 React reconciliation）
  kind: SMCMarkerKind;
  timestamp: string;             // ISO 8601 date
  // 對於箭頭類（BOS/CHoCh）：
  price?: number;                // 標記放在哪個價格高度
  // 對於矩形類（FVG/OB）：
  rangeStart?: { time: string; price: number };
  rangeEnd?: { time: string; price: number };
  active: boolean;               // FVG 是否仍未被填補；OB 是否仍 valid
  description: string;           // tooltip 顯示文字（i18n key 套用後）
  rule: string;                  // 判定規則簡述（"3-bar gap, > 0.5% threshold"）
}
```

**渲染規則**（對應 spec FR-009 ~ FR-014）：
- BOS_BULL：綠色向上箭頭（▲）+ 文字「BOS」
- BOS_BEAR：紅色向下箭頭（▼）+ 文字「BOS」
- CHOCH_BULL／BEAR：金色箭頭 + 文字「CHoCh」
- FVG：半透明矩形（藍色 active／灰色 filled）
- OB：半透明矩形（綠色 demand／紅色 supply），active 與 untested 用實線、tested 用虛線

---

## 5. Reward 分解（圖表用）

### 5.1 RewardSeries

```typescript
interface RewardSeries {
  cumulative: RewardCumulativePoint[];
  byStep: RewardSnapshot[];     // 與 trajectory 同長度，index 對齊
}

interface RewardCumulativePoint {
  step: number;
  cumulativeTotal: number;
  cumulativeReturn: number;
  cumulativeDrawdownPenalty: number;
  cumulativeCostPenalty: number;
}
```

**圖表元件**：`RewardBreakdown.tsx` 渲染為 stacked-bar（每步），下方搭配 line（累積總獎勵）。

---

## 6. Policy 相關

### 6.1 PolicyOption

對應 GET `/api/v1/policies` 陣列元素，用於 `PolicyPicker.tsx`。

```typescript
interface PolicyOption {
  policyId: string;
  policyVersion: string;
  displayName: string;       // 例："PPO-SMC v1.2 (2026-03-15)"
  trainedAt: string;         // ISO 8601 datetime
  trainingDataRange: { start: string; end: string };
  configSummary: string;     // 短描述，例："NVDA+AMD+TSM, 5y daily, w_dd=0.3"
  metrics: {
    sharpeRatio: number;
    maxDrawdown: number;
    cumulativeReturn: number;
  };
  active: boolean;           // 是否為 production 預設
}
```

---

## 7. 推論請求／回應

### 7.1 InferRequestViewModel

對應 POST `/api/v1/infer` 請求。

```typescript
interface InferRequestViewModel {
  policyId: string;
  policyVersion?: string;        // 省略則用 latest
  observation: number[];         // 維度由 003 env 決定（例 24）
  idempotencyKey?: string;       // 由 client 產生，UUID v4
}
```

### 7.2 InferResponseViewModel

```typescript
interface InferResponseViewModel {
  action: ActionVector;
  policyId: string;
  policyVersion: string;
  inferredAt: string;            // ISO 8601 datetime
  latencyMs: number;             // server 端量測
}
```

---

## 8. 設定／使用者偏好

### 8.1 UserPreferences

存於 `localStorage`，key = `warroom.preferences.v1`。

```typescript
interface UserPreferences {
  language: 'zh-TW' | 'en';
  theme: 'light' | 'dark' | 'system';
  defaultPolicyId?: string;
  chartGridlines: boolean;
  numberLocale: 'en-US' | 'zh-TW';   // 影響千分位符號（英文 , 中文 ,）
  timezone: 'UTC' | 'local';
}
```

**Default**：
```typescript
const defaults: UserPreferences = {
  language: 'zh-TW',
  theme: 'system',
  chartGridlines: true,
  numberLocale: 'en-US',     // USD 金額慣用英式千分位
  timezone: 'UTC',           // 對齊回測資料時區
};
```

---

## 9. 錯誤處理 ViewModel

### 9.1 ApiErrorViewModel

對應 006 Gateway 統一錯誤 envelope（見 006 contracts/error-codes.md）。

```typescript
interface ApiErrorViewModel {
  code: string;              // 例："POLICY_NOT_FOUND"
  message: string;           // server 提供的英文訊息
  i18nKey?: string;          // 前端可選用：errors.policyNotFound
  httpStatus: number;
  traceId: string;           // 對應 Gateway X-Trace-Id
  details?: Record<string, unknown>;
  retryable: boolean;        // 由 code 決定（5xx 與 timeout 為 true）
}
```

**i18n mapping**（補充於 `contracts/i18n-keys.md`）：每個 server 錯誤 code 對應一條前端
i18n key，找不到則 fallback 到 `errors.unknown`。

---

## 10. 路由 URL 狀態

URL hash 格式：

```
#/<page>?<param>=<value>&...

example:
#/trajectory?episodeId=abc-123&from=2025-06-01&to=2025-12-31&zoomStart=2025-08-01&zoomEnd=2025-09-30
```

```typescript
interface OverviewParams {
  policyId?: string;
}

interface TrajectoryParams {
  episodeId: string;
  from?: string;       // 縮放區間起
  to?: string;         // 縮放區間訖
  zoomStart?: string;
  zoomEnd?: string;
}

interface DecisionParams {
  episodeId?: string;
  step?: number;
  // 若無 episodeId：使用即時 SSE 模式
  policyId?: string;
}
```

URL state 由 `useSearchParams()`（React Router）+ Zod schema 解析；解析失敗則導向預設值。

---

## 11. View Model 與 API DTO 轉換契約

| API DTO（006 envelope）| ViewModel | 轉換邏輯 |
|----------------------|-----------|---------|
| `EpisodeSummaryDto`  | `EpisodeSummaryViewModel` | 1:1（status enum 字串對齊）|
| `EpisodeDetailDto`   | `EpisodeDetailViewModel` | 額外 hydrate `rewardBreakdown` from trajectory |
| `TrajectoryFrameDto` | `TrajectoryFrame` | smcSignals 由 backend 直接提供；對 NaN fvgDistancePct 保留為 `NaN` |
| `PolicyMetadataDto`  | `PolicyOption` | `displayName` 由 frontend 組合 |
| `InferActionDto`     | `ActionVector` | 1:1 |
| `ErrorEnvelope`      | `ApiErrorViewModel` | 由 `i18nKeyMap[code]` 決定 i18n key |

轉換函式集中於 `src/api/envelopes.ts`，每個轉換都附 unit test（`tests/unit/envelopes.test.ts`）。

---

## 12. 不變條件總表（前端可在 dev mode 用 `console.assert` 驗證）

1. 任一 trajectory frame：`weights.riskOn + weights.riskOff + weights.cash ≈ 1`
2. `weights.perAsset` 加總 ≈ `riskOn + riskOff`
3. `reward.total ≈ reward.returnComponent - reward.drawdownPenalty - reward.costPenalty`
4. `EpisodeSummaryViewModel.status === 'completed'` ⇒ `totalReturn`、`maxDrawdown`、
   `sharpeRatio` 皆為有限數字
5. `EpisodeDetailViewModel.trajectoryUri` 與 `trajectoryInline` 互斥
6. `SMCMarker.kind` 為 BOS／CHoCh ⇒ 必有 `price`，無 `rangeStart/rangeEnd`
7. `SMCMarker.kind` 為 FVG／OB ⇒ 必有 `rangeStart` 與 `rangeEnd`，`price` 可選
8. `UserPreferences.theme === 'system'` ⇒ 渲染時依 `prefers-color-scheme` 決定

違反不變條件時：dev 環境 `console.assert` 警示；prod 環境靜默並上報 `data_invariant_violation`
事件（未來監控接入點）。
