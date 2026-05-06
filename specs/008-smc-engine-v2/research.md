# Research: SMC Engine v2

**Feature**: 008-smc-engine-v2
**Date**: 2026-05-05
**Phase**: 0 — 設計決策研究

本 feature 沒有 [NEEDS CLARIFICATION] markers——spec 階段所有開放問題均已收斂。本研究文件記錄三個關鍵設計決策的「為什麼選 A 不選 B」，作為 plan/tasks/implement 階段的判斷依據。

---

## Decision 1：BOS dedup 採「每 swing 一次」而非「每段 trend 一次」

### Decision

維護 `used_swing_high: set[int]` 與 `used_swing_low: set[int]`（以 `swing.bar_index` 為 key）。某個 swing 一旦被 close 突破過（不論是否觸發 BOS 還是 CHoCh），即加入 used；後續 K 棒對同一 swing 的突破不再產生 event。

新 swing 形成後（`swing_high_marker[i] = True`），`last_swing_high` 切換到新位置；新 swing 不在 used 集合內，可被突破一次。

### Rationale

- **「每段 trend 一次」過嚴**：trend = bullish 內出現多個越來越高的 swing high；agent 應該每個都能感知到突破（HH 連發），這是 SMC 教科書的「order flow continuation」。若整段 trend 只發一次 BOS，會錯過所有 follow-up 突破。
- **「每 swing 一次」剛好**：每個 swing 是一個獨立的「測試點」；突破測試成功（close 越過）發 event 一次，後續價格高於該水平不再算「事件」，符合「事件 vs 狀態」的區分。
- **對 RL agent 的學習意義**：每個 BOS event 在 episode 中是一個 sparse reward-relevant signal。dedup 後 event 數從原本的「滿足條件的 K 棒數」（雜訊 ~50 倍）降到「結構性突破次數」（信號）。

### Alternatives Considered

- **A. 不 dedup**（v1 行為）：被否決——導致同一事件重複觸發，RL credit assignment 失效。
- **B. 每段 trend 一次**：被否決——丟失 trend 內 follow-up 突破的訊號。
- **C. 用「距離前次 BOS ≥ N bar」當 dedup**：被否決——參數 N 難調，且仍然把不同 swing 的突破合在一起。

---

## Decision 2：OB 由 break event 觸發，找 break 之前最後一根反向 K

### Decision

`ob.py` 改為提供 `build_obs_from_breaks(breaks, opens, closes, highs, lows, valid_mask, ob_lookback_bars) -> list[OrderBlock]`。對每筆 break：

- bullish break（BOS_BULL / CHOCH_BULL）→ 從 `break.bar_index - 1` 起往前找最後一根 close < open 的紅 K → 該 K 的 [low, high] 為 OB 範圍。
- bearish break 對稱（找綠 K）。
- lookback 範圍 `[break.bar_index - ob_lookback_bars, break.bar_index - 1]`，找不到反向 K 則該 break 無 OB（不產出，但 break event 仍記錄）。

每個 OB 物件帶 `source_break_index`（在 `breaks` 列表中的位置）與 `source_break_kind`。

### Rationale

- **語意正確**：SMC 教科書定義「OB = 造成結構突破前的最後一根反向 K 棒」。v1 的 swing-driven 寫法是把 OB 跟 swing 綁定，但 swing 本身不一定觸發 break——導致大量「孤兒 OB」。
- **可追溯**：每個 OB 都能還原其觸發事件，前端可在 hover 時顯示「來自 2024-03-15 的 BOS_BULL」，paper 可寫「N 個 OB 平均每個對應 K.K 個 break」。
- **數量上界**：`len(obs) ≤ len(breaks)`，自然稀疏化（v1 的 OB ≈ swing 數，本來就過密）。

### Alternatives Considered

- **A. 保留 swing-driven 並後處理過濾**：被否決——後處理過濾屬於 hack（fixture builder 已嘗試過 `ob_used` set），引擎內部仍然是錯的。
- **B. OB 用 swing-driven 但加「曾被觸碰」過濾**：被否決——「觸碰」與「造成 break」是兩件事，不能等同。
- **C. break-driven 但 OB 範圍取「整段 displacement candle 群」**：被否決——增加複雜度，且 v1 規則已是「最後一根反向 K」，保持向後對齊。

### 失效規則保留 v1 行為

時間失效（`current_bar_index > formation_bar_index + ob_lookback_bars`）+ 結構失效（bullish OB close < bottom；bearish close > top）。沿用 v1 是為了：

1. 失效規則本身與 break-driven 無關，無需改。
2. 失效規則改動會影響 `ob_touched` / `ob_distance_ratio` 觀測值分布——v2 已經改了「OB 從哪來」，不再多動「OB 怎麼結束」，控制變因。

---

## Decision 3：FVG 用 ATR 相對過濾，預設 ratio 0.25

### Decision

新增 `SMCFeatureParams.fvg_min_atr_ratio: float = 0.25`。FVG 偵測時：

```
keep_fvg = (top - bottom) / atr[bar_index] >= fvg_min_atr_ratio  (當 atr[bar_index] 非 NaN)
keep_fvg = (top - bottom) / mid_price >= fvg_min_pct              (當 atr[bar_index] 為 NaN — warmup 期)
```

兩條件**並列**而非串聯：ATR 可用時優先用 ATR；否則退化用既有 `fvg_min_pct` 絕對比例（保留 v1 兜底）。

### Rationale

- **不同價位資產的公平性**：NVDA $500 上一個 $1 缺口（0.2%）與 GLD $200 上一個 $1 缺口（0.5%）的「市場意義」差距，靠絕對 % 無法區分。ATR 能反映「該資產該時期的典型波動」，把 FVG 高度標準化到「幾倍日波動」。
- **預設值 0.25 的依據**：
  - 業界開源工具大多不過濾（密度過高）；
  - 學術論文（FVG/imbalance 量化）多用 0.25 ~ 0.5；
  - 0.25 對 daily 資料約等於「至少 1/4 個典型日波動」——肉眼可見的缺口；
  - 留給 paper ablation 掃 `[0.1, 0.25, 0.5]` 的中心值。
- **可調 hyperparam**：寫成 `SMCFeatureParams` 欄位而非 hardcode，方便未來 ablation。

### Alternatives Considered

- **A. 純絕對 %（v1）**：被否決——資產間不公平。
- **B. 用 K 棒實際 range 過濾（不算 ATR）**：被否決——單根 K 的 range 雜訊大，不如 ATR 平滑。
- **C. ratio 預設 0.5**：被否決——太嚴，會丟過多中型 FVG，RL 學到的「FVG 距離」channel 變稀疏到 NaN 過多。
- **D. ratio 預設 0.1**：被否決——過鬆，密度跟 v1 接近，未解決問題。

### ATR NaN 退化邏輯

當 `atr[i] = NaN`（通常為 warmup 期 i < atr_window）：
- 不放棄該 FVG，改用 `fvg_min_pct` 絕對下限判定。
- 這保證資料前 14 根（atr_window=14）仍能偵測 FVG，否則整段 warmup 都會無 FVG，影響 PPO 訓練前期。
- **不**用「ATR=NaN 時直接保留」——會繞過所有過濾。
- **不**用「ATR=NaN 時直接丟棄」——warmup 期 FVG 完全消失太激進。

---

## 三項決策的綜合影響

| 維度 | v1 | v2 |
|---|---|---|
| BOS event 數（NVDA 8 年 daily） | ~600（重複） | ~50（事件） |
| OB 數 | ~250（綁 swing） | ~50（綁 break） |
| FVG 數 | ~700 | < 200（ATR 過濾後） |
| RL observation channel 介面 | 5 channel int8/float | **不變** |
| PPO env 介面 | 不變 | **不變** |
| reward function | 不變 | **不變**（NON-NEGOTIABLE） |

**Phase 0 完成 — 無未解決問題，進 Phase 1**。
