# Feature Specification: SMC Engine v2 — 規則化結構事件偵測

**Feature Branch**: `008-smc-engine-v2`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "SMC engine v2 — 把現有 SMC 引擎從『逐根 K 棒信號』改成『結構化事件 + signal array』；解決 BOS 重複發信號、OB 與 break 脫鉤、FVG 沒按波動度過濾的問題。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — RL Agent 拿到事件型 BOS / CHoCh 信號（Priority: P1）

研究員訓練 PPO 時，希望每個結構性突破事件只在「真正發生的那根 K 棒」觸發一次 ±1 的訊號，而不是「持續滿足條件的 50 根 K 棒都報 +1」。這讓 agent 學到的是「**事件 → 行為**」的因果，而不是被一個長尾的 latching state 稀釋訓練梯度。

**Why this priority**：這是整個改造的核心動機。如果這條沒做，後面 OB / FVG 改動的視覺差異無法翻譯成 RL 訓練品質提升。同時，這個改動會直接影響 PPO observation 分布，必須與其他規則同步切換。

**Independent Test**：在一段已知有「連續 50 根 K close 高於前 swing high」的歷史資料上跑引擎，檢查 `bos_signal` 陣列只在第一根=+1，其餘 49 根=0；同時 `breaks` 事件清單只回 1 筆 BOS event，附 anchor swing 的 time/price。

**Acceptance Scenarios**：

1. **Given** 一段價格序列在第 t 根 K close 首次突破 last_swing_high，且第 t+1...t+49 根仍持續高於該 swing high，
   **When** 引擎跑完 batch_compute，
   **Then** `bos_signal[t] = +1` 且 `bos_signal[t+1..t+49] = 0`；`breaks` 列表只有一筆 BOS_BULL，其 anchor_swing_price = 該 swing high，break_price = close[t]。

2. **Given** trend 為 bullish 且 close[t] 同時 > last_swing_high 又 < last_swing_low（不可能但作為衝突保險），
   **When** 引擎判定，
   **Then** CHoCh 優先；`choch_signal[t] = -1`、`bos_signal[t] = 0`，且 `breaks` 列表只記 CHoCh 一筆。

3. **Given** 同一個 swing high 已被突破過（產出 BOS event 並 mark used），後續價格再次衝破同一 price level，
   **When** 引擎處理後續 K 棒，
   **Then** 不再產出 BOS event，`bos_signal` 陣列在該位置為 0。

---

### User Story 2 — Order Block 由結構突破觸發，數量與 break 對齊（Priority: P1）

戰情室視覺化檢視時，每個 OB 矩形必須對應一個明確的結構事件（BOS 或 CHoCh）。研究員不再需要看到每個 swing 點都生一個 OB（目前 v1 行為導致 OB 矩形比 swing 多、且大量 OB 從未被任何 break 引用）。

**Why this priority**：與 P1 並列。OB 是 SMC 「smart money 進場區」的核心 POI，定義必須能被回溯到一個 break event。這也是 paper 描述「程式化 SMC」站得住腳的關鍵——每個 OB 都有 `source_break` 可追溯。

**Independent Test**：在同一段資料上跑 v2 引擎，比對 `obs` 列表長度與 `breaks` 列表長度。每個 OB 物件可被獨立查詢其 `source_break_index`，並驗證對應 break 的 direction 與 OB direction 一致（bullish break → bullish OB，反之）。

**Acceptance Scenarios**：

1. **Given** 引擎處理完一段資料產生 N 筆 break events，
   **When** 檢查 `obs` 列表，
   **Then** OB 數量 ≤ N（若某 break 往回找不到反向 K 棒則該 break 無 OB），且每個 OB 物件都有 `source_break_index` 指向對應 break 在 `breaks` 列表中的位置。

2. **Given** 一個 BOS_BULL event 在第 t 根 K 觸發，
   **When** 引擎建立對應 OB，
   **Then** OB direction = bullish，formation_bar_index 為 [0, t-1] 範圍內最後一根 close < open 的紅 K 位置；OB 的 top/bottom 為該紅 K 的 high/low。

3. **Given** swing 點出現但未引發 break（例如 swing high 之後價格一直在區間內震盪），
   **When** 引擎處理該段資料，
   **Then** 不產生任何 OB（v1 行為會生 OB，v2 必須不生）。

---

### User Story 3 — FVG 按波動度過濾，去除微小無效缺口（Priority: P2）

戰情室與 RL observation 都需要「有意義」的 FVG。價格 $500 的 NVDA 上一個 $0.5 的小缺口（0.1% 波動）跟價格 $200 的 GLD 上 $1 的缺口（0.5%）是不同量級——絕對 % 過濾不公平，必須用 ATR-relative。

**Why this priority**：P2，因為視覺改善明顯但不影響核心結構事件邏輯。即使這條沒做完，P1/P2 的 BOS+OB 改造已能解決大部分密度問題。

**Independent Test**：在同一段 NVDA 8 年 daily 資料上，分別用 `fvg_min_atr_ratio = 0.0`（不過濾）與 `0.25` 跑引擎，比較 FVG 數量。後者應顯著減少（觀察值 < 200 筆/8 年/單資產）。

**Acceptance Scenarios**：

1. **Given** SMCFeatureParams.fvg_min_atr_ratio = 0.25 且 ATR(14) 在某 K 棒為 5.0，
   **When** 該位置出現一個 (top - bottom) = 1.0 的 FVG（ratio = 0.2 < 0.25），
   **Then** 該 FVG 不被加入 fvgs 列表，且不影響後續 fvg_distance_pct 計算（該位置取下一個合格 FVG 或 NaN）。

2. **Given** SMCFeatureParams.fvg_min_atr_ratio = 0.25，同一條件下高度 1.5（ratio = 0.3 ≥ 0.25），
   **When** 引擎處理，
   **Then** 該 FVG 被保留，正常進入後續 fill / 距離計算。

3. **Given** 使用者把 fvg_min_atr_ratio 設為 0.0，
   **When** 引擎處理，
   **Then** 等價於 v1 行為（不做 ATR 過濾，僅保留 fvg_min_pct 絕對下限）。

---

### User Story 4 — 結構事件的可追溯資料結構（Priority: P2）

研究員（與未來 paper reviewer）需要對每個 BOS / CHoCh 事件回答「這個事件斷的是哪個 swing？什麼時間？什麼價位？事件後 trend 變成什麼？」。引擎必須輸出帶完整 anchor 資訊的 event 物件，而不是只有 ±1 的 signal array。

**Why this priority**：P2，是 P1 的衍生。signal array 對 RL 已足夠，但對前端視覺與 paper 可追溯性，必須有 event 物件。

**Independent Test**：對任一 break event，可獨立驗證它的 `anchor_swing_time` 對應到引擎之前確認過的某個 swing point，且 `anchor_swing_price` 等於該 swing 的 high/low。

**Acceptance Scenarios**：

1. **Given** 引擎產出一筆 BOS_BULL event，
   **When** 檢視該 event 物件，
   **Then** 物件含 `kind = "BOS_BULL"`、`time`（突破當下 K 棒時間）、`break_price`（close[t]）、`anchor_swing_time`、`anchor_swing_price`、`trend_after = "bullish"`。

2. **Given** trend 從 bullish → bearish 的 CHoCh event，
   **When** 檢視該 event 物件，
   **Then** `kind = "CHOCH_BEAR"`、`trend_after = "bearish"`、`anchor_swing_*` 對應到被跌破的 last_swing_low。

---

### Edge Cases

- **Neutral trend 起始期**：序列開頭尚無前一 swing 序列建立 trend，第一個結構性突破應如何處理？決議：在 neutral 狀態下，第一次 close 突破任何已確認 swing 視為「初始 BOS」（trend_after 設定為對應方向），後續才能發生 CHoCh。
- **Swing 點與 break 同根 K 棒**：若第 t 根 K 棒同時被偵測為 swing high（fractal 確認的延遲 swing）且 close 突破前一 swing，**先發 break event 再更新 swing 位置**，避免「自己突破自己」。
- **Bar gaps（非交易日）**：日線資料天然有週末跳空，FVG 三根 K 邏輯仍按 bar index 連續處理，不另做日曆對齊。
- **OB 找不到反向 K**：若 break 之前的 lookback 窗口內全是同向 K 棒（極端單邊行情），對應 break 不產生 OB，event 仍記錄但 obs 列表少一筆——不算錯誤。
- **FVG 在過濾邊界**：`(top-bottom)/atr` 等於 ratio 時採 `>=`（保留），與單元測試對齊。
- **Invalid bars（valid_mask=False）**：依舊不參與 swing / break / OB / FVG 偵測（沿用 spec FR-015 行為）。

## Requirements *(mandatory)*

### Functional Requirements

**FR-001 — Swing 偵測（保留 v1 行為）**
系統必須以左右 fractal lookback (`swing_length`) 偵測 swing high / swing low，採嚴格不等比較，valid_mask=False 的位置不參與。**v2 不修改此模組行為**。

**FR-002 — Close 突破為 BOS / CHoCh 的唯一觸發條件**
系統必須僅以 K 棒收盤價（close）對 last_swing_high / last_swing_low 的相對位置判定 BOS / CHoCh，不採用 high/low 影線。

**FR-003 — 同一 swing 只能被突破一次**
系統必須維護「已被突破的 swing」標記。一旦 last_swing_high 因某根 K 棒 close 突破而觸發 BOS 或 CHoCh，後續 K 棒 close 仍高於該 price level 不再重複觸發；下一次突破必須等待新的 swing high 形成成為 last_swing_high。

**FR-004 — CHoCh 優先於 BOS**
若同一根 K 棒同時滿足 BOS 與 CHoCh 條件（理論上互斥，但作衝突保險），系統必須先判 CHoCh，並設 `bos_signal = 0`、`choch_signal ∈ {-1, +1}`。

**FR-005 — Trend 狀態管理**
系統必須維護 `trend ∈ {bullish, bearish, neutral}`。CHoCh 翻轉 trend；BOS 不改變 trend；neutral 初始狀態下第一次結構性突破將 trend 設定為對應方向（**初始 BOS**，不發 CHoCh）。

**FR-006 — Structure event 物件輸出**
系統必須輸出 `breaks: list[StructureBreak]`。每筆物件含：
- `kind ∈ {BOS_BULL, BOS_BEAR, CHOCH_BULL, CHOCH_BEAR}`
- `time`（突破當下 K 棒時間戳）
- `bar_index`（突破當下 K 棒位置）
- `break_price`（突破當下 close）
- `anchor_swing_time`（被突破的 swing 時間）
- `anchor_swing_bar_index`
- `anchor_swing_price`（被突破的 swing high/low 價位）
- `trend_after`（事件處理完的 trend 狀態）

**FR-007 — Signal array 與 event 列表並行輸出**
系統必須同時回傳 dedup 後的 `bos_signal: int8[n]` 與 `choch_signal: int8[n]`，事件當下=±1、其餘=0；以及 `breaks` 列表。兩者內容必須一致（每個 event 對應 array 上一個非零位置）。**signal array 的 shape 與資料型別必須與 v1 相同**（PPO observation 介面不變）。

**FR-008 — OB 由 break event 觸發**
系統必須在每筆 break event 產生時，往回從 `bar_index - 1` 起在 `[0, bar_index-1]` 範圍內找最後一根反向 K 棒（bullish break 找 close<open 的紅 K，bearish break 找 close>open 的綠 K），以該 K 棒的 [low, high] 為 OB 範圍。

**FR-009 — OB 物件可追溯到 source break**
每個 OB 物件必須含 `source_break_index`（在 breaks 列表中的位置）與 `source_break_kind`，前端與分析腳本可由此還原 OB 的觸發事件。

**FR-010 — OB 失效規則（保留 v1 行為）**
OB 失效仍由（a）時間（`current_bar_index > formation_bar_index + ob_lookback_bars`）或（b）結構（bullish OB close < bottom；bearish OB close > top）兩擇一觸發，邏輯沿用 v1。

**FR-011 — FVG ATR 相對過濾**
系統必須在 FVG 偵測階段加上 `fvg_min_atr_ratio` 參數（預設 0.25，可調）。當 `(top - bottom) / atr[bar_index] < fvg_min_atr_ratio` 時忽略該 FVG。若 ATR 該位置為 NaN（窗口未就緒），FVG 仍按其他規則決定是否保留——不因 ATR NaN 全部丟掉。

**FR-012 — FVG 三根 K 規則（保留）**
Bullish FVG：`high[i-2] < low[i]`，`top = low[i]`、`bottom = high[i-2]`；Bearish FVG 對稱。範圍偵測本身的邏輯不變。

**FR-013 — RL observation 介面不變**
SMC observation 仍為 5 個 channel：`bos_signal`、`choch_signal`、`fvg_distance_pct`、`ob_touched`、`ob_distance_ratio`。維度、資料型別、缺失值表示（NaN / 0）皆與 v1 相同。**v2 改變的是各 channel 的數值分布，不改變介面**。

**FR-014 — Incremental 模式同步更新**
若引擎提供 incremental（單根 K 餵入）路徑（`src/smc_features/incremental.py`），必須與 batch 路徑採用同一套規則，產出相同的 break events 與 signal array。

**FR-015 — 不保留 legacy 模式**
v2 一次切換完成。`SMCFeatureParams` 不新增 `legacy_mode` flag，舊行為僅能透過 git 歷史回溯。

### Key Entities

- **StructureBreak**：一個結構性突破事件，記錄 BOS 或 CHoCh 發生的時間、價位、被突破的 anchor swing、事件後 trend。
- **OrderBlock (v2)**：在 v1 欄位基礎上新增 `source_break_index`、`source_break_kind` 兩個追溯欄位，formation_bar_index 仍指向反向 K 棒位置。
- **FairValueGap (v2)**：欄位與 v1 相同，僅在偵測階段加 ATR 過濾。
- **SMCFeatureParams (v2)**：新增 `fvg_min_atr_ratio: float`（預設 0.25），其他欄位（swing_length, fvg_min_pct, ob_lookback_bars, atr_window）保留。

## Success Criteria *(mandatory)*

### Measurable Outcomes

**SC-001 — BOS 訊號稀疏化**
單一資產 8 年 daily 資料上，v2 的 `bos_signal` 非零位置數 ≤ v2 的 `breaks` 列表中 BOS 事件數（嚴格相等是理想；放寬到「不可能更多」即通過）。

**SC-002 — OB 與 break 對齊**
單一資產 8 年 daily 資料上，v2 的 OB 列表長度 ≤ break 列表長度，且每個 OB 都能查到合法的 `source_break_index`（無孤兒 OB）。

**SC-003 — FVG 視覺密度顯著下降**
對 NVDA 2018–2026 daily 資料，使用 `fvg_min_atr_ratio = 0.25` 後 FVG 數量相較
不過濾（ratio=0.0）至少下降 25%，且絕對數量 ≤ 500。實測：v1 約 697 → v2 約
451（35% 下降）。原始 spec 目標「<200」為事前估計值，實測發現要達到該絕對門檻
需把 ratio 拉到 ~1.0，會把 RL observation 的 FVG channel 稀疏到無訊號，故將
門檻調整為「相對下降 + 絕對上限」雙條件，兼顧 RL 訓練密度與視覺合理性。

**SC-004 — RL observation 介面零破壞**
PPO env reset/step 介面不變、observation shape 不變、reward function 不變。既有 PPO 訓練腳本（不改任何 import 或型別）必須能直接吃 v2 引擎輸出。

**SC-005 — 事件物件完整性**
100% 的 `StructureBreak` 物件具備所有必填欄位（kind / time / bar_index / break_price / anchor_swing_time / anchor_swing_bar_index / anchor_swing_price / trend_after），無 None 值（neutral→bullish 的初始 BOS 例外：anchor_swing_* 必須對應實際存在的 swing point）。

**SC-006 — 規則化判定的可重現性**
給定同一份 OHLCV 與同一組 SMCFeatureParams，跨次執行（含 incremental vs batch）產出的 breaks 列表（含順序與所有欄位值）必須完全相同（byte-identical 等價於 deterministic）。

**SC-007 — 戰情室視覺密度合理**
fixture 重生並載入 War Room 後，KLine 上顯示的 BOS / CHoCh / OB / FVG 矩形與線條密度，符合 TradingView SMC indicator 一般使用體驗（單畫面 ≤ 30 個結構標記）。**此項由人工視覺檢查驗收，非自動化**。

## Assumptions

- 既有 PPO 訓練（500k steps，~30 分鐘）會在 v2 落地後重訓，hyperparam 可能需要 retune（entropy_coef / clip_range）但不在本 feature 範圍內。
- War Room fixture builder（`apps/warroom/scripts/parquet_to_ohlc_fixture.py`）的修改屬於 feature 007 範疇，本 feature 只保證引擎輸出的事件物件結構足夠 builder 直接消費，無須前端額外 reverse-engineer。
- FVG 過濾比預設 0.25 為「初始實驗值」，未來 paper 寫 ablation 時可能掃 [0.1, 0.25, 0.5] 三個值，但 v2 落地不需要此 ablation。
- Feature 001 的 contract test（`tests/contract/`）會被擴充而非重寫——signal array 仍然存在，只是值的分布變化；新增的 break 事件物件需要新測試覆蓋。
- v2 不更動 ATR 計算（`src/smc_features/atr.py`），仍用同樣的 `atr_window`（預設 14）。
- `SMCFeatureParams` 為 dataclass，新增欄位 `fvg_min_atr_ratio` 採 keyword-only 方式加入，不破壞既有位置呼叫。
- v1 在 Phase 1–7 已落地的 swing 偵測模組（`swing.py`）行為與 contract 完全保留——本 feature 不重構 swing。
