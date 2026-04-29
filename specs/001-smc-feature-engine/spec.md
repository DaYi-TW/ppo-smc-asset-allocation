# Feature Specification: SMC 特徵量化引擎

**Feature Branch**: `001-smc-feature-engine`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 SMC（Smart Money Concepts）特徵量化引擎，從 OHLCV 時序資料計算 BOS/CHoCh/FVG/OB 等量化特徵，供下游 PPO 觀測空間使用，並提供 K 線視覺化工具供人工覆核。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 研究者批次計算 SMC 特徵 (Priority: P1)

ML 研究者手上有一段歷史 OHLCV 資料（例如 NVDA 兩年日線），想將其轉換為 PPO 訓練可用的觀測序列。研究者呼叫單一函式，傳入 DataFrame 與一組特徵參數（例如 swing length），得到擴增後的 DataFrame，內含 BOS/CHoCh 訊號、FVG 距離、OB 觸碰狀態等特徵欄位，可直接餵入後續 RL 環境。

**Why this priority**: 這是整個引擎的核心價值產出，缺此功能則下游 PPO 訓練 feature 無法啟動。其他 user story 都是建立在批次計算結果之上。

**Independent Test**: 取一段公開可重現的歷史日線資料，呼叫批次計算函式，驗證輸出 DataFrame 包含所有約定特徵欄位、列數與輸入一致、數值在有效域內（例如 BOS/CHoCh 限定 {-1, 0, 1}）。

**Acceptance Scenarios**:

1. **Given** 一段含 500 根 K 棒的有效 OHLCV DataFrame，**When** 呼叫批次特徵計算函式，**Then** 回傳的 DataFrame 列數為 500、原欄位完整保留、新增 `bos_signal`、`choch_signal`、`fvg_distance_pct`、`ob_touched`、`ob_distance_ratio` 五個欄位。
2. **Given** 同一段 DataFrame 與同一組參數，**When** 連續執行兩次特徵計算，**Then** 兩次輸出 DataFrame 在所有欄位上 byte-identical（包含 NaN 位置一致）。
3. **Given** OHLCV DataFrame 中有一根明顯突破前波段高點的 K 棒，**When** 計算 BOS 特徵，**Then** 該 K 棒位置的 `bos_signal` 為 `1`（向上突破），其前後相鄰 K 棒為 `0`。

---

### User Story 2 - 論文審查者視覺化覆核特徵 (Priority: P2)

論文審查者或不熟悉 SMC 的同事看到一份特徵 DataFrame，懷疑某根被標記為 BOS 的 K 棒是否真的符合 SMC 定義。審查者呼叫視覺化函式，輸入原始 OHLCV 與特徵 DataFrame、指定時間區段，得到 K 線圖（PNG 或 HTML）並疊加 BOS/CHoCh/FVG/OB 標記，可在 5 分鐘內肉眼確認演算法判定正確性。

**Why this priority**: 直接對應憲法 Principle II（特徵可解釋性）— 不可解釋的特徵在本專案禁止。此 user story 是 P1 之後的第一道品質防線，沒有它則無法在論文審查或 PR review 中獨立驗證 P1 結果。

**Independent Test**: 給定 P1 輸出與一個已知會觸發 BOS 的 K 棒位置，呼叫視覺化函式產出圖檔，圖中可清楚看到該 K 棒被標記、且 BOS 的前波段高點位置以水平線或文字標註。

**Acceptance Scenarios**:

1. **Given** 一份含特徵欄位的 DataFrame 與時間區段 [t1, t2]，**When** 呼叫視覺化函式並指定輸出格式為 PNG，**Then** 產出檔案為有效 PNG、解析度足以辨識 K 線本體與標記文字。
2. **Given** 區段內含一個 FVG 訊號，**When** 視覺化輸出該區段，**Then** FVG 缺口以陰影或矩形區塊覆蓋於對應價位，並標示「未填補」或「已填補」狀態。
3. **Given** 一個從未接觸 SMC 的使用者拿到 PNG 與一份兩段話的圖例說明，**When** 觀察圖檔，**Then** 該使用者能在 5 分鐘內指出哪根 K 棒被判定為 BOS 並說出原因（突破前高/前低）。

---

### User Story 3 - 後端工程師增量計算單根 K 棒 (Priority: P3)

未來實盤推論時，每根新 K 棒收盤後系統需即時更新最新一列特徵，不可能對整段歷史重算。後端工程師呼叫增量函式，傳入既有的特徵 DataFrame（含內部狀態）與一根新 OHLCV 列，得到僅含新一列特徵的結果，計算延遲極低，可滿足實盤即時性要求。

**Why this priority**: 為未來「微服務化 + 實盤」預留 API 介面；當前研究階段非必須，但若不於本 feature 預留設計，後續服務化將需重寫核心邏輯。優先序低於 P1/P2 因為當前回測不依賴此模式。

**Independent Test**: 取一段 N 根 K 棒，先以批次模式產出全部 N 列特徵；再以前 N-1 根批次計算 + 第 N 根用增量模式，驗證兩種方式產出的第 N 列特徵 byte-identical。

**Acceptance Scenarios**:

1. **Given** 已對前 499 根 K 棒完成批次計算的特徵 DataFrame 與第 500 根的 OHLCV 列，**When** 呼叫增量計算函式，**Then** 回傳僅含第 500 列特徵的結果，且其內容與「對全部 500 根做批次計算後取最後一列」完全相等。
2. **Given** 一段 1000 根 K 棒的歷史，**When** 連續呼叫 1000 次增量計算（每次餵入下一根），**Then** 每次呼叫的計算延遲 < 10 ms（在開發者一般筆電硬體上）。

---

### User Story 4 - 研究者餵入瑕疵資料的容錯處理 (Priority: P4)

研究者拿到的歷史資料常含缺值（NaN）、停牌跳空、零成交量等品質問題。研究者期望引擎能在這些列上明確標示「特徵不可用」（例如該列特徵為 NaN）而非靜默丟棄列、也不應 crash，使研究者在後續分析時能精準辨識哪些 K 棒不可用於訓練。

**Why this priority**: 資料品質容錯雖重要，但在 P1 已交付且資料先經過品質清洗的情境下，研究者可手動排除瑕疵列。此 user story 提升便利性與安全性，但非阻塞 MVP。

**Independent Test**: 構造一個含已知瑕疵（如連續 5 列收盤價為 NaN、一列 volume 為 0）的 DataFrame，呼叫批次計算，驗證輸出列數與輸入相同，瑕疵列的特徵為 NaN 或約定哨兵值，且函式無例外拋出。

**Acceptance Scenarios**:

1. **Given** 一段 500 根 K 棒、其中第 100~104 列 close 為 NaN 的 DataFrame，**When** 呼叫批次計算，**Then** 輸出 DataFrame 共 500 列、第 100~104 列特徵欄位為 NaN、其餘列特徵正常計算、無例外拋出。
2. **Given** 一段含一根 volume = 0 的停牌 K 棒，**When** 呼叫批次計算，**Then** 該列特徵被標示為「無效」（NaN 或哨兵值），且後續 K 棒的特徵計算不受該列污染（例如 swing 偵測不將該列納入波段判定）。

---

### Edge Cases

- **資料量不足**：當輸入 DataFrame 列數少於特徵所需的最小視窗（例如 swing length = 50 但只給 30 根 K 棒），所有特徵欄位為 NaN，函式不拋出例外。
- **DataFrame index 非單調遞增或含重複 timestamp**：函式在計算前驗證並拋出明確的 ValueError，訊息說明錯誤位置。
- **欄位名稱大小寫或缺漏**：缺少必要欄位（open/high/low/close/volume 任一）時，拋出明確的 KeyError，訊息列出缺少的欄位名。
- **跨大缺口（如停牌後跳空 30%）**：BOS/CHoCh 判定不應將跳空誤判為趨勢突破；定義上 swing 偵測須基於連續有效 K 棒。
- **未填補的 FVG 永久存在**：當資料末段含一個從未被回填的 FVG，`fvg_distance_pct` 應持續輸出與該缺口的距離，不應因「過期」而靜默清除。
- **同根 K 棒同時觸發 BOS 與 CHoCh**：定義上互斥（CHoCh 表示反向轉折，BOS 表示同向延續），spec 須明確規定衝突時的優先序（建議：CHoCh 優先，因其代表結構性轉變更具事件意義）。
- **增量模式被以非連續時間呼叫**：例如跳過數根 K 棒餵入，函式應偵測 timestamp 不連續並拋出明確錯誤，提示呼叫方改用批次模式重算。

## Requirements *(mandatory)*

### Functional Requirements

#### 核心特徵計算

- **FR-001**: 系統 MUST 提供批次計算函式，接收符合 schema 的 OHLCV DataFrame 與一組特徵參數，回傳擴增後的 DataFrame 含所有 SMC 特徵欄位。
- **FR-002**: 系統 MUST 計算 `bos_signal` 與 `choch_signal` 欄位，值域限定為 {-1, 0, 1}，分別代表向下訊號、無訊號、向上訊號。
- **FR-003**: 系統 MUST 計算 `fvg_distance_pct` 欄位，表示當前收盤價距離最近一個未填補 FVG 的百分比距離；若無未填補 FVG 則輸出 NaN。
- **FR-004**: 系統 MUST 計算 `ob_touched` 欄位（boolean）與 `ob_distance_ratio` 欄位（float），分別表示當前 K 線是否觸碰最近 Order Block，以及收盤價距離 Order Block 中心價位的標準化比例。
- **FR-005**: BOS、CHoCh、FVG、OB 的判定規則 MUST 在對應特徵函式的 docstring 中以數學形式或精確自然語言描述，使第三方可依描述獨立實作出等價結果。

#### 可重現性與一致性

- **FR-006**: 給定相同輸入 DataFrame 與相同特徵參數，系統 MUST 在同一 commit 下產出 byte-identical 的輸出 DataFrame（含欄位順序、dtype、NaN 位置）。
- **FR-007**: 系統 MUST 不依賴系統時間、隨機性、或浮點非決定性運算（例如多執行緒 reduce）；所有計算 MUST 為單執行緒 deterministic。
- **FR-008**: 系統 MUST 支援批次與增量兩種計算模式；增量模式對單根新 K 棒的輸出 MUST 與批次模式對應位置的輸出完全相等。

#### 視覺化覆核

- **FR-009**: 系統 MUST 提供視覺化函式，接收 OHLCV 與特徵 DataFrame、時間區段參數，產出 candlestick 圖檔並疊加 BOS/CHoCh/FVG/OB 標記。
- **FR-010**: 視覺化輸出 MUST 支援 PNG 與 HTML 兩種格式擇一，由呼叫方指定。
- **FR-011**: 視覺化結果 MUST 為每個被觸發的特徵標示其判定依據（例如 BOS 同時標出被突破的前波段高/低點位置）。

#### 資料品質容錯

- **FR-012**: 系統 MUST 在輸入 DataFrame 缺少必要欄位時拋出 KeyError，訊息列出缺少的欄位名。
- **FR-013**: 系統 MUST 在輸入 DataFrame 的 index 非單調遞增或含重複 timestamp 時拋出 ValueError，訊息指出第一個違規位置。
- **FR-014**: 對於資料品質瑕疵的列（NaN、零成交量），系統 MUST 在對應列的特徵欄位輸出 NaN 或約定哨兵值，且 MUST NOT 從輸出 DataFrame 中刪除該列。
- **FR-015**: 系統 MUST 將資料瑕疵列排除於後續特徵的滾動視窗計算外（例如 swing 偵測不納入 NaN 列），避免污染下游列的特徵值。

#### 介面與使用方式

- **FR-016**: 系統 MUST 以純 Python 函式庫（package）形式提供，不含 Web 服務、不含訊息中介、不含資料庫存取。
- **FR-017**: 所有特徵判定參數（例如 swing length、ATR window、FVG 最小缺口幅度）MUST 由呼叫方顯式傳入；系統不提供自動調參或預設參數最佳化。
- **FR-018**: 系統 MUST 提供使用範例（quickstart 文件或 example script），示範如何從 OHLCV 載入到產出特徵到視覺化的完整流程。

#### 衝突處理

- **FR-019**: 當同一根 K 棒同時符合 BOS 與 CHoCh 條件時，系統 MUST 以 CHoCh 優先（`choch_signal` 非零、`bos_signal` 為 0），並在 docstring 中聲明此優先序。

### Key Entities *(include if feature involves data)*

- **OHLCV Bar**：單根 K 棒，含開盤/最高/最低/收盤/成交量五欄與 timestamp index。為所有特徵計算的最小資料單位。
- **Feature-augmented DataFrame**：原始 OHLCV 加上 SMC 特徵欄位（`bos_signal`、`choch_signal`、`fvg_distance_pct`、`ob_touched`、`ob_distance_ratio`），列數與 timestamp 與輸入完全對齊。
- **Swing Point**：由 swing length 參數定義的局部高/低點，作為 BOS 與 CHoCh 判定的基準。為內部中介概念，可選擇性暴露為輔助欄位供視覺化使用。
- **Fair Value Gap (FVG)**：三根 K 棒形成的價格不連續區間（具體規則於實作 docstring 中定義）。具狀態：未填補 / 已填補。
- **Order Block (OB)**：在趨勢反轉前最後一根反向 K 棒所佔據的價格區間。具屬性：上下緣價位、形成時間、有效/失效狀態。
- **Feature Parameters**：使用者顯式傳入的設定組合，至少包含 swing length、ATR window、FVG 最小幅度、OB 有效期。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 給定 NVDA 2023-01-01 至 2024-12-31 的日線資料（約 500 根 K 棒），引擎在開發者一般筆電硬體上 30 秒內完成全部特徵批次計算。
- **SC-002**: 對於相同 commit、相同輸入、相同參數，跨平台（Linux、macOS、Windows）執行的輸出 DataFrame 在所有非 NaN 浮點欄位上的最大絕對誤差 ≤ 1e-9。
- **SC-003**: 增量計算單根 K 棒的延遲 < 10 ms（同一硬體基準）。
- **SC-004**: 所有特徵函式的單元測試覆蓋率 ≥ 90%（以 line coverage 計）；每個特徵 MUST 至少有一組正面案例與一組反面案例。
- **SC-005**: 從未接觸 SMC 的使用者，在獲得一段視覺化輸出與一頁圖例說明後，能在 5 分鐘內正確指出 80% 以上 BOS / CHoCh 標記的判定依據。
- **SC-006**: 對含 5% 瑕疵列（NaN 或 volume=0）的 DataFrame 執行批次計算，輸出 DataFrame 列數與輸入一致、瑕疵列特徵為 NaN、無例外拋出。

## Assumptions

- 假設輸入 DataFrame 已由呼叫方完成資料抓取、欄位命名標準化、時區對齊（資料抓取本身不在本 feature 範圍內）。
- 假設特徵將被下游 PPO 環境消費，因此採用 NaN 作為「無資料/不可用」的哨兵值（PPO 環境須自行處理 NaN，例如 forward fill 或排除）。此選擇優先於使用具體大數值哨兵，以避免污染神經網路梯度。
- 假設 SMC 演算法的具體判定規則（例如 FVG 的精確邊界定義、OB 的有效期上限）將於實作階段（plan/research）依文獻與實務慣例固定，並寫入 docstring 作為規格的延伸。本 spec 僅約束「規則必須明文且可重現」，不在 spec 層級鎖死特定數學公式。
- 假設視覺化的「圖例說明」由呼叫方或本 feature 同步交付的 quickstart 文件提供；視覺化函式本身不負責圖例文案撰寫。
- 假設增量模式的 < 10 ms 延遲基準在「單一檔案/單一商品」下成立；多商品並行處理由呼叫方自行排程，不在本 feature 內負責。
- 假設「開發者一般筆電硬體」基準為：x86_64 CPU、≥ 8 GB RAM、SSD（不限定具體型號），SC-001 與 SC-003 在此基準下評估。
