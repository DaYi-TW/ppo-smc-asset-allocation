# Feature Specification: 資料抓取與快照管理（Data Ingestion & Snapshot Management）

**Feature Branch**: `002-data-ingestion`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "從 Yahoo Finance 抓六檔股票/ETF 日線（NVDA, AMD, TSM, MU, GLD, TLT）與 FRED 3-month T-bill rate（DTB3），時間範圍 2018-01-01 至 2026-04-29，產出可重現的 Parquet 快照與 metadata，commit 進 repo 供下游 feature 使用。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 研究者一次性建立可重現資料快照 (Priority: P1)

ML 研究者在新環境（新 clone 的 repo、新筆電、新合作者）需要從零建立完整的歷史資料集供 PPO 訓練與回測使用。研究者執行單一抓取指令，系統依序連線 Yahoo Finance 與 FRED，下載六檔資產與一支利率序列的歷史日線，存為 Parquet 快照並產出對應 metadata，全部檔案落於 `data/raw/`。研究者隨後將整個 `data/raw/` 目錄 commit 進 repo，使任何後續 clone 此 commit 的人取得 byte-identical 的資料集。

**Why this priority**: 沒有資料就沒有後續所有 feature。本 user story 是整個專案資料層的基礎，且直接落實憲法 Principle I（可重現性）— commit-level 的資料快照是論文可重現的根基。

**Independent Test**: 在新環境執行抓取指令，驗證 `data/raw/` 產出 6 個 OHLCV Parquet + 1 個利率 Parquet + 對應 metadata JSON；隨機抽兩檔開啟，確認欄位、列數、時間範圍符合規格。

**Acceptance Scenarios**:

1. **Given** 一個乾淨的 repo clone 與有效網路連線，**When** 研究者執行抓取指令，**Then** `data/raw/` 產出 7 個 Parquet 檔（6 股票/ETF + 1 利率）與 7 個對應 metadata JSON 檔，總執行時間 < 5 分鐘。
2. **Given** 上述快照已產生，**When** 任何研究者讀取 `data/raw/nvda_daily_20180101_20260429.parquet`，**Then** 回傳 DataFrame 含 `open`、`high`、`low`、`close`、`volume`、`quality_flag` 六個欄位，index 為遞增的交易日 timestamp。
3. **Given** 兩個獨立環境在同一 commit 下執行抓取指令，**When** 比對兩端產出的 Parquet 檔，**Then** 在重新抓取時間相同的前提下，兩端 SHA-256 雜湊一致；若抓取時間不同（資料源後續修訂），metadata 中的 `fetch_timestamp_utc` 不同但 `data_source_call_params` 一致。

---

### User Story 2 - 任何使用者驗證本地快照未被竄改 (Priority: P2)

論文審查者、合作者或 CI 流程拿到一份本地 `data/raw/` 後，希望確認快照與 metadata 一致（檔案未被部分修改、沒有遺漏、SHA-256 與紀錄相符）。使用者執行驗證指令，系統依序讀取每個 Parquet、重算 SHA-256、與 metadata 中的雜湊比對，最後輸出全綠或精確指出哪一檔不符。

**Why this priority**: 直接守護憲法 Principle I — 沒有驗證機制，「commit-level 可重現」只是口號。本 story 為 P2 是因為它依賴 P1 已產出快照，但本身對下游所有 feature 的可信度提供保證。

**Independent Test**: 對未污染的 `data/raw/` 執行驗證指令，得「全部通過」；手動修改任一 Parquet 的單一 byte，再次執行，得「失敗 + 指出該檔名 + 顯示預期 vs. 實際雜湊」。

**Acceptance Scenarios**:

1. **Given** 一份完整未污染的 `data/raw/` 目錄，**When** 使用者執行驗證指令，**Then** 退出代碼為 0，輸出列出每個檔案與其「OK」狀態。
2. **Given** `data/raw/nvda_daily_20180101_20260429.parquet` 中某個 byte 被修改，**When** 執行驗證指令，**Then** 退出代碼為非 0，錯誤訊息明確指出 `nvda_daily_20180101_20260429.parquet` 的雜湊不符，並列出 metadata 中紀錄的雜湊與重算雜湊。
3. **Given** `data/raw/` 中缺少某個快照檔（例如使用者誤刪），**When** 執行驗證指令，**Then** 退出代碼為非 0，錯誤訊息列出缺少的檔名。

---

### User Story 3 - 研究者擴展時間範圍重建快照 (Priority: P3)

研究者決定將回測延伸至更早的歷史（例如改為 2015-01-01 開始）或更新到最新交易日。研究者修改抓取設定的時間參數，執行重建指令，系統覆寫舊快照、產出新 metadata、並提示研究者新的快照雜湊與檔名。研究者比對新舊 metadata，確認改動如預期。

**Why this priority**: 重建流程在當前研究階段非每日必要，但若不於本 feature 預設清楚的重建路徑，未來擴展資料時將出現「半手動 + 半 commit」的混亂狀態，破壞可重現性。優先序低於 P1/P2 因為一次性快照已能支撐 MVP 階段。

**Independent Test**: 修改設定的起始日期，執行重建指令，驗證 `data/raw/` 中新 Parquet 列數較舊版多、metadata 的時間範圍欄位已更新、SHA-256 不同於舊版。

**Acceptance Scenarios**:

1. **Given** 既有 `data/raw/` 與一份修改後的設定（起始日期由 2018-01-01 改為 2015-01-01），**When** 研究者執行重建指令，**Then** 所有 7 個 Parquet 與 metadata 被覆寫，新 metadata 的 `data_source_call_params.start` 為 `2015-01-01`，列數較舊版增加。
2. **Given** 重建過程中 yfinance 對某一檔回傳網路錯誤，**When** 抓取流程進行至該檔，**Then** 流程不留下半完成的中介檔案（要嘛全部成功覆寫，要嘛保留舊版本）；錯誤訊息明確指出失敗檔名與原始錯誤。

---

### User Story 4 - 下游 feature 載入快照進行特徵計算 (Priority: P2)

SMC 特徵引擎開發者（feature 001）或 PPO 訓練者執行訓練腳本，腳本內部讀取 `data/raw/` 中對應資產的 Parquet 為 pandas DataFrame，立即可餵入 SMC 特徵函式。載入過程不需任何資料清洗、欄位重命名或缺值處理（資料品質政策已於本 feature 落實）。

**Why this priority**: 此 user story 是 002 與 001 之間的契約點，直接決定 001 能否啟動實作。與 P2 並列因為它與「驗證」同等是「P1 之後立刻需要」的能力。

**Independent Test**: 撰寫一段 6 行 Python 腳本，讀取 NVDA Parquet 為 DataFrame，呼叫 `df.head()` 與 `df.dtypes`，驗證輸出欄位、dtype、index 型別符合 spec 約定。

**Acceptance Scenarios**:

1. **Given** 已產出的 `data/raw/nvda_daily_20180101_20260429.parquet`，**When** 下游程式以標準 Parquet 讀取 API 載入，**Then** 載入時間 < 100 ms，回傳 DataFrame 直接符合 feature 001 spec 的輸入 schema（`open`/`high`/`low`/`close`/`volume` 欄位 + datetime index）。
2. **Given** 載入後的 DataFrame 含 `quality_flag` 欄位，**When** 下游程式以 `quality_flag == "ok"` 篩選，**Then** 回傳子集所有列均為有效資料，無需額外缺值檢查。

---

### Edge Cases

- **某資產在指定區間內退市或暫停交易**（如 yfinance 對 TSM 回傳空 DataFrame）：系統應拋出明確錯誤指出哪檔失敗，而非靜默產出空 Parquet。
- **FRED 對 DTB3 在指定區間內缺值**（聯邦假日、資料延遲）：缺值列保留於 Parquet 中、`quality_flag` 標示 `"missing_rate"`，不靜默插值。
- **yfinance 回傳重複日期 row**（過往實務上偶發）：偵測到重複時保留首次出現的列，於 `quality_flag` 標示 `"duplicate_dropped"`，並在 metadata 紀錄遭丟棄列數。
- **網路完全斷線**：抓取指令在合理重試次數後 fail-fast，明確說明「無法連線 yahoofinance.com / api.stlouisfed.org」，且不留下任何中介檔案。
- **磁碟空間不足**：寫檔失敗時拋出清楚錯誤訊息，且已寫出的部分檔案應被自動清除（避免半完成狀態）。
- **Parquet 寫入因 schema mismatch 失敗**（極罕見，例如 yfinance 改變欄位 dtype）：拋出明確訊息指出哪一欄 dtype 不符預期。
- **使用者本地時區與 UTC 不同**：所有 metadata 的 timestamp 欄位以 UTC 紀錄、附上 ISO 8601 + `Z` 後綴，避免時區歧義。
- **重建時舊快照部分檔案被使用者鎖定（Windows）**：抓取指令偵測到無法覆寫時，明確指出該檔被佔用，請使用者關閉占用程序後重試。

## Requirements *(mandatory)*

### Functional Requirements

#### 抓取與輸出

- **FR-001**: 系統 MUST 提供單一抓取指令，一次完成全部六檔股票/ETF 與一支利率序列的下載。
- **FR-002**: 系統 MUST 對每個資產產出獨立的 Parquet 檔，落於 `data/raw/` 目錄；檔名規約為 `<ticker_lower>_<frequency>_<startYYYYMMDD>_<endYYYYMMDD>.parquet`（例如 `nvda_daily_20180101_20260429.parquet`、`dtb3_daily_20180101_20260429.parquet`）。
- **FR-003**: 系統 MUST 對每個 Parquet 產出對應的 metadata JSON 檔，命名為 Parquet 檔名末綴 `.meta.json`（例如 `nvda_daily_20180101_20260429.parquet.meta.json`）。
- **FR-004**: Parquet 檔 MUST 採用 snappy 壓縮。
- **FR-005**: 抓取的時間範圍 MUST 為 2018-01-01（含）至 2026-04-29（含）；時間範圍由設定檔顯式提供，使用者可修改後重建。
- **FR-006**: 股票/ETF 價格 MUST 為除權息調整後的價格（透過資料源的 `auto_adjust=True` 等價設定）。

#### 資料 Schema 與品質

- **FR-007**: 股票/ETF 的 Parquet MUST 含欄位 `open`、`high`、`low`、`close`、`volume`、`quality_flag`，index 為交易日 timestamp（無時區或 UTC，需明確聲明）。
- **FR-008**: 利率資料的 Parquet MUST 含欄位 `rate_pct`、`quality_flag`，index 為日期 timestamp。
- **FR-009**: `quality_flag` MUST 取自一組明確列舉的字串值（至少包含 `"ok"`、`"missing_close"`、`"zero_volume"`、`"missing_rate"`、`"duplicate_dropped"`），以下游可直接以字串比對篩選。
- **FR-010**: 系統 MUST NOT 對缺值執行前向填補、線性插值或任何形式的修補；缺值列保留於 Parquet、`quality_flag` 對應標示。
- **FR-011**: 偵測到重複 timestamp 時，系統 MUST 保留首次出現的列、丟棄後續重複，並於 metadata 中紀錄遭丟棄的列數與其原始 timestamp。

#### Metadata 與可重現性

- **FR-012**: 每個 metadata JSON MUST 至少包含下列欄位：`fetch_timestamp_utc`（ISO 8601 含 `Z`）、`data_source`（如 `"yfinance"` 或 `"fred"`）、`data_source_call_params`（原始呼叫參數的鍵值對）、`upstream_package_versions`（資料抓取套件名稱與版本）、`sha256`（對應 Parquet 的雜湊）、`row_count`、`column_schema`（欄位名與 dtype）、`time_range`（起訖 timestamp）。
- **FR-013**: SHA-256 MUST 對 Parquet 檔的二進位內容計算（非對 DataFrame 邏輯內容），以使任何 byte-level 改動皆能偵測。
- **FR-014**: 系統 MUST 在抓取前以系統時間（UTC）產生 `fetch_timestamp_utc`，且不得使用本地時區。

#### 驗證與重建

- **FR-015**: 系統 MUST 提供驗證指令，掃描 `data/raw/` 中所有 Parquet 與 metadata，重算 SHA-256 並比對；任一不符或缺檔，退出代碼非 0。
- **FR-016**: 驗證指令的錯誤訊息 MUST 指出具體檔名、預期雜湊、實際雜湊（若不符）或「missing」（若缺檔）。
- **FR-017**: 系統 MUST 提供重建指令（可與抓取指令為同一指令的不同模式），執行時覆寫既有快照與 metadata。
- **FR-018**: 抓取或重建過程中若任一資產失敗（網路錯誤、退市、API 限流），系統 MUST 提供「全部成功才寫入」或「保留先前版本」的原子性保證；不留下部分成功的不一致狀態。

#### 錯誤處理與重試

- **FR-019**: 對暫時性錯誤（網路逾時、HTTP 5xx、rate limit）系統 MUST 執行有限次數的重試（具體策略由 plan 階段決定，建議使用指數退避）。
- **FR-020**: 對永久性錯誤（HTTP 4xx 非 limit、symbol 不存在、FRED series ID 錯誤）系統 MUST 立即停止重試並回傳明確錯誤訊息（含 ticker、HTTP 狀態碼或 API 訊息）。
- **FR-021**: 所有錯誤訊息 MUST 為使用者可直接判讀的繁體中文或英文（擇一即可）；不應僅呈現原始 stack trace。

#### 範圍邊界（顯式排除以避免 scope creep）

- **FR-022**: 系統 MUST NOT 計算任何衍生指標（如 SMC 特徵、技術指標、報酬率）；輸出僅為原始 OHLCV 與利率。
- **FR-023**: 系統 MUST NOT 提供日內（intraday/分鐘級）資料抓取；僅日線。
- **FR-024**: 系統 MUST NOT 內建排程器或 cron；不做每日自動更新（觸發抓取由使用者顯式執行）。
- **FR-025**: 系統 MUST NOT 為資料源切換提供抽象介面；本 feature 僅鎖定 Yahoo Finance（OHLCV）與 FRED（利率）兩個來源。

### Key Entities *(include if feature involves data)*

- **Asset Snapshot**：單一資產的歷史 OHLCV 資料快照。屬性：ticker、頻率（日線）、時間範圍、列數、SHA-256、原始呼叫參數。
- **Rate Snapshot**：單一利率序列快照（DTB3）。屬性：series ID、時間範圍、列數、SHA-256、原始呼叫參數。
- **Snapshot Metadata**：與每個快照一對一的 metadata 紀錄，承載可重現性所需的所有上下文（抓取時間、套件版本、雜湊、欄位 schema 等）。
- **Quality Flag**：每列資料的品質狀態標示，列舉值含 `ok` / `missing_close` / `zero_volume` / `missing_rate` / `duplicate_dropped`。
- **Ingestion Configuration**：使用者可修改的設定（時間範圍、ticker 清單、輸出目錄）。修改後執行重建指令即觸發新快照產生。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 從零執行抓取指令到產出全部 7 個 Parquet 與 7 個 metadata JSON，在 50 Mbps 以上家用網路環境下總耗時 < 5 分鐘。
- **SC-002**: 驗證指令對未污染的快照回傳退出代碼 0、所有檔案標示「OK」；對任何快照單字節改動回傳退出代碼非 0、訊息精確指出該檔名與雜湊不符細節。
- **SC-003**: 載入單一資產 Parquet 為 DataFrame 的時間 < 100 ms（一般 SSD 硬體基準）。
- **SC-004**: 抓取或重建過程中任一資產失敗，`data/raw/` 不出現「部分新檔 + 部分舊檔」的混合狀態（原子性保證）。
- **SC-005**: 全部 6 檔股票/ETF 快照加上 1 檔利率快照的總檔案大小 < 10 MB（控制 repo 體積）。
- **SC-006**: 對「symbol 不存在」「網路斷線」「FRED 無此序列」三種典型錯誤情境，使用者在不閱讀本 feature 任何原始碼的情況下，可從錯誤訊息直接定位問題並修正。
- **SC-007**: 同一 commit 下兩位獨立研究者執行抓取指令，若資料源未在兩次抓取間修訂歷史資料，兩端產出的 Parquet 檔內容（不含 metadata 中的 `fetch_timestamp_utc`）byte-identical。

## Assumptions

- 假設使用者擁有有效的網路連線可存取 `query2.finance.yahoo.com` 與 `api.stlouisfed.org`；本 feature 不負責 VPN 或 proxy 設定。
- 假設使用者已（或願意）取得 FRED API key 並透過環境變數提供。FRED API 為免費註冊使用，註冊流程不在本 feature 範圍。
- 假設「一般網路環境」指 ≥ 50 Mbps 家用寬頻，SC-001 的 5 分鐘基準在此前提下評估。
- 假設「一般 SSD 硬體」指 NVMe 或 SATA SSD，SC-003 的 100 ms 基準在此前提下評估。
- 假設 yfinance 與 fredapi 在抓取時點仍為公開可用、無需付費；若資料源未來政策變更（例如 Yahoo Finance 改為付費），需於新 feature 中重新評估。
- 假設下游 feature（特別是 001-smc-feature-engine）將以 pandas 標準 Parquet 讀取 API 載入快照；本 feature 的 schema 設計以 pandas 慣例為基準（datetime index、float64 數值、object 字串欄位）。
- 假設「2018-01-01 至 2026-04-29」涵蓋四個 regime（2018 升息尾聲、2020 COVID、2022 升息、2023-2026 AI 行情），符合論文預設的回測情境。若日後論文範圍變更，由 user story 3 的重建流程處理。
- 假設 metadata 紀錄的「套件版本」鎖定在 `requirements.txt` / `pyproject.toml` 中（dependency lock 機制由實作層級決定）；本 feature 僅紀錄抓取當下的版本，不負責 dependency 鎖定。
- 假設「現金部位」在後續 PPO feature 中使用 DTB3 的日報酬等價值（即 `(1 + rate_pct/100) ** (1/252) - 1`）；本 feature 僅交付原始 rate_pct，不做此轉換。
