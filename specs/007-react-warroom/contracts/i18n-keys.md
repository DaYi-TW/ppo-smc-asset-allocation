# i18n Keys Contract

**Feature**: 007-react-warroom
**Date**: 2026-04-29

定義戰情室前端國際化 key 命名規約、zh-TW 與 en 對照表，以及錯誤碼到 i18n key 的映射。

---

## 命名規範

格式：`<scope>.<component>.<element>` 三段式（最多四段，僅 errors 用兩段）。

| Scope         | 用途                                         |
|---------------|----------------------------------------------|
| `app`         | 應用層級（標題、共用名詞）                   |
| `nav`         | 導覽列、側欄                                 |
| `overview`    | Overview 頁面                                |
| `trajectory`  | Trajectory 頁面                              |
| `decision`    | Decision 頁面                                |
| `settings`    | Settings 頁面                                |
| `chart`       | 跨頁面共用的圖表元素（圖例、軸標）           |
| `panel`       | 跨頁面共用的面板（policy picker、reward）    |
| `common`      | 共用元素（按鈕、表格 header、確認對話框）    |
| `errors`      | 錯誤訊息（API 錯誤碼對應）                   |
| `units`       | 單位（USD、%、days）                         |

---

## zh-TW 與 en 對照表（核心 keys）

### app.*

| Key                        | zh-TW                            | en                                |
|----------------------------|----------------------------------|-----------------------------------|
| `app.title`                | PPO-SMC 戰情室                   | PPO-SMC War Room                  |
| `app.subtitle`             | 強化學習資產配置研究展示         | RL Asset Allocation Research Demo |
| `app.loading`              | 載入中…                          | Loading…                          |
| `app.empty`                | 暫無資料                         | No data available                 |
| `app.retry`                | 重試                             | Retry                             |
| `app.cancel`               | 取消                             | Cancel                            |
| `app.confirm`              | 確認                             | Confirm                           |
| `app.copy`                 | 複製                             | Copy                              |
| `app.copied`               | 已複製                           | Copied                            |

### nav.*

| Key                  | zh-TW         | en                  |
|----------------------|---------------|---------------------|
| `nav.overview`       | 戰情總覽      | Overview            |
| `nav.trajectory`     | 軌跡分析      | Trajectory          |
| `nav.decision`       | 決策面板      | Decision            |
| `nav.settings`       | 偏好設定      | Settings            |
| `nav.skipToMain`     | 跳到主內容    | Skip to main content|

### overview.*

| Key                                | zh-TW                  | en                            |
|------------------------------------|------------------------|-------------------------------|
| `overview.title`                   | 戰情總覽               | Overview                      |
| `overview.weightChart.title`       | 資產權重分配           | Asset Weight Allocation       |
| `overview.weightChart.legend.riskOn`  | 攻擊型（AI 半導體）  | Risk-On (AI Semiconductors)   |
| `overview.weightChart.legend.riskOff` | 避險型（黃金、債券） | Risk-Off (Gold, Bonds)        |
| `overview.weightChart.legend.cash` | 現金                   | Cash                          |
| `overview.navChart.title`          | 淨值與最大回撤         | NAV & Max Drawdown            |
| `overview.navChart.navAxis`        | 淨值（USD）            | NAV (USD)                     |
| `overview.navChart.drawdownAxis`   | 回撤（%）              | Drawdown (%)                  |
| `overview.summary.totalReturn`     | 總報酬                 | Total Return                  |
| `overview.summary.sharpeRatio`     | 夏普比率               | Sharpe Ratio                  |
| `overview.summary.maxDrawdown`     | 最大回撤               | Max Drawdown                  |
| `overview.summary.totalSteps`      | 總交易日               | Total Trading Days            |

### trajectory.*

| Key                                  | zh-TW                       | en                            |
|--------------------------------------|-----------------------------|-------------------------------|
| `trajectory.title`                   | 軌跡分析                    | Trajectory Analysis           |
| `trajectory.kline.title`             | K 線圖（NVDA）+ SMC 標記    | K-Line (NVDA) + SMC Markers   |
| `trajectory.kline.legend.bos`        | BOS（結構破壞）             | BOS (Break of Structure)      |
| `trajectory.kline.legend.choch`      | CHoCh（結構轉變）           | CHoCh (Change of Character)   |
| `trajectory.kline.legend.fvg`        | FVG（公允價值缺口）         | FVG (Fair Value Gap)          |
| `trajectory.kline.legend.ob`         | OB（訂單區）                | OB (Order Block)              |
| `trajectory.smcFilter.label`         | SMC 標記過濾                | SMC Marker Filter             |
| `trajectory.episodePicker.label`     | 選擇 Episode                | Select Episode                |
| `trajectory.tooltip.bos.bull`        | 看漲結構破壞於 {{date}}（{{rule}}） | Bullish BOS at {{date}} ({{rule}}) |
| `trajectory.tooltip.bos.bear`        | 看跌結構破壞於 {{date}}（{{rule}}） | Bearish BOS at {{date}} ({{rule}}) |
| `trajectory.tooltip.fvg`             | FVG 缺口 {{rangeStart}}—{{rangeEnd}}，{{state}} | FVG {{rangeStart}}—{{rangeEnd}}, {{state}} |
| `trajectory.tooltip.ob`              | {{kind}} OB 於 {{rangeStart}}，{{state}} | {{kind}} OB at {{rangeStart}}, {{state}} |
| `trajectory.tooltip.fvgState.active` | 未填補                      | Unfilled                      |
| `trajectory.tooltip.fvgState.filled` | 已填補                      | Filled                        |

### decision.*

| Key                                    | zh-TW                      | en                            |
|----------------------------------------|----------------------------|-------------------------------|
| `decision.title`                       | 決策面板                   | Decision Panel                |
| `decision.observation.title`           | 觀測值                     | Observation                   |
| `decision.observation.col.feature`     | 特徵                       | Feature                       |
| `decision.observation.col.value`       | 數值                       | Value                         |
| `decision.observation.col.normalized`  | 正規化                     | Normalized                    |
| `decision.action.title`                | 動作向量                   | Action Vector                 |
| `decision.action.logProb`              | log-probability：{{value}} | log-probability: {{value}}    |
| `decision.action.entropy`              | 熵：{{value}}              | Entropy: {{value}}            |
| `decision.reward.title`                | 獎勵分解                   | Reward Breakdown              |
| `decision.reward.return`               | 報酬項                     | Return Component              |
| `decision.reward.drawdownPenalty`      | 回撤懲罰                   | Drawdown Penalty              |
| `decision.reward.costPenalty`          | 成本懲罰                   | Cost Penalty                  |
| `decision.reward.total`                | 總獎勵                     | Total Reward                  |
| `decision.narration.template`          | 模型於 {{date}} 採取動作 {{action}}：因 {{rationale}} | Model took action {{action}} at {{date}} because {{rationale}} |
| `decision.live.connecting`             | 連線中…                    | Connecting…                   |
| `decision.live.open`                   | 即時推論中                 | Live inference active         |
| `decision.live.closed`                 | 連線已關閉                 | Connection closed             |
| `decision.live.reconnect`              | 重新連線                   | Reconnect                     |

### settings.*

| Key                              | zh-TW                | en                       |
|----------------------------------|----------------------|--------------------------|
| `settings.title`                 | 偏好設定             | Settings                 |
| `settings.language.label`        | 介面語言             | Interface Language       |
| `settings.language.zhTW`         | 繁體中文             | Traditional Chinese      |
| `settings.language.en`           | English              | English                  |
| `settings.theme.label`           | 主題                 | Theme                    |
| `settings.theme.light`           | 亮色                 | Light                    |
| `settings.theme.dark`            | 暗色                 | Dark                     |
| `settings.theme.system`          | 跟隨系統             | Follow System            |
| `settings.defaultPolicy.label`   | 預設 Policy          | Default Policy           |
| `settings.timezone.label`        | 時區                 | Timezone                 |
| `settings.timezone.utc`          | UTC                  | UTC                      |
| `settings.timezone.local`        | 本機時區             | Local Timezone           |
| `settings.save`                  | 儲存設定             | Save Settings            |
| `settings.saved`                 | 已儲存               | Saved                    |

### units.*

| Key                | zh-TW       | en              |
|--------------------|-------------|-----------------|
| `units.usd`        | 美元（USD） | USD             |
| `units.percent`    | %           | %               |
| `units.bps`        | bps         | bps             |
| `units.days`       | 天          | days            |
| `units.steps`      | 步          | steps           |

### errors.*

對應 006 Gateway error code（見 006 contracts/error-codes.md）：

| Key                                | zh-TW                              | en                                         |
|------------------------------------|------------------------------------|--------------------------------------------|
| `errors.unknown`                   | 發生未知錯誤，請稍後再試           | An unknown error occurred. Please retry.   |
| `errors.network`                   | 網路連線失敗                       | Network connection failed                  |
| `errors.policyNotFound`            | 找不到指定的 Policy                | Policy not found                           |
| `errors.episodeNotFound`           | 找不到指定的 Episode               | Episode not found                          |
| `errors.observationDimMismatch`    | 觀測值維度錯誤                     | Observation dimension mismatch             |
| `errors.observationNaN`            | 觀測值含有 NaN，請檢查上游資料     | Observation contains NaN                   |
| `errors.rateLimitExceeded`         | 請求過於頻繁，請稍候再試           | Rate limit exceeded                        |
| `errors.circuitOpen`               | 後端服務暫時不可用，請稍候再試     | Backend service unavailable (circuit open) |
| `errors.gatewayTimeout`            | Gateway 逾時                       | Gateway timeout                            |
| `errors.authInvalidToken`          | 授權 Token 無效，請重新登入        | Invalid auth token                         |
| `errors.authExpiredToken`          | 授權 Token 已過期，請重新登入      | Auth token expired                         |
| `errors.idempotencyConflict`       | 偵測到重複請求衝突                 | Idempotency conflict                       |
| `errors.validationFailed`          | 輸入資料驗證失敗：{{detail}}       | Validation failed: {{detail}}              |
| `errors.serverInternal`            | 伺服器內部錯誤（trace: {{traceId}}）| Server internal error (trace: {{traceId}}) |
| `errors.sse.connectionFailed`      | 即時連線失敗                       | SSE connection failed                      |
| `errors.sse.disconnected`          | 連線中斷                           | Disconnected                               |

---

## 插值規則

- 用 `{{var}}` 表示變數插入（i18next 預設語法）。
- 數值與日期變數必須在傳入前**已格式化**（避免 i18n 端做格式化造成國際化偏差）。

```typescript
// ❌ 錯：把 raw number 丟給 i18next
t('decision.action.logProb', { value: -0.234567 });

// ✅ 對：先用 utils/format 處理
t('decision.action.logProb', { value: formatNumber(-0.234567, { fractionDigits: 4 }) });
```

---

## Pluralization 與性別

本專案中文不需 plural；英文僅少數場景：

```json
// en.json
{
  "trajectory.frameCount_one": "{{count}} frame",
  "trajectory.frameCount_other": "{{count}} frames"
}
```

zh-TW 對應僅一條（`trajectory.frameCount`: `{{count}} 筆`）。

---

## 翻譯維護流程

1. PR 新增／修改 key 必須同時更新 `zh-TW.json` 與 `en.json`。
2. CI step：執行 `npm run i18n:check` 驗證兩檔 key 集合一致（用 `i18next-parser`）。
3. 若英文版尚未翻譯，先放預設值並標 `// TODO(en): translate`，CI 會 warn 不 fail。

```yaml
# CI 範例
- run: npm run i18n:check
  # 缺 key → exit 1（fail）
  # 內容為 // TODO → exit 0（warn only）
```

---

## 動態文案與 Markdown

對於含格式（粗體、連結）的訊息，使用 `<Trans>` 元件而非純字串：

```tsx
<Trans i18nKey="decision.narration.template" values={{ date, action, rationale }}>
  Model took action <strong>{{action}}</strong> at {{date}} because {{rationale}}.
</Trans>
```

避免在訊息內嵌 HTML 字串（XSS 風險）。
