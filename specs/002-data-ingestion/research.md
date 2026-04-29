# Phase 0 Research: 002-data-ingestion

**Date**: 2026-04-29
**Spec**: [spec.md](./spec.md)

本文件解決 plan.md Technical Context 中所有 NEEDS CLARIFICATION 與 spec.md 涉及的關鍵
未知數，作為 Phase 1 設計與後續實作的決策依據。所有決策皆須與憲法 v1.1.0 Principle I
（可重現性，NON-NEGOTIABLE）對齊。

---

## R1：股票/ETF 資料源 client 選擇

**Decision**: 採用 `yfinance` ≥ 0.2.40，配合 `auto_adjust=True` 取得除權息調整後價格。

**Rationale**:
- spec.md 已明文指定 Yahoo Finance + `auto_adjust=True`（FR-006）。
- `yfinance` 為現存最廣泛使用之非官方 Yahoo Finance Python client，社群維護活躍、
  文件完整；與 FinRL、qlib 等下游 RL 框架已驗證相容。
- `auto_adjust=True` 在 yfinance ≥ 0.2 預設將 `Close` 欄位替換為 adjusted close、
  `Open/High/Low` 同步調整，免去呼叫方自行計算 split / dividend factor。

**Alternatives considered**:
- **官方 Yahoo Finance API**：已關閉公開存取，不可行。
- **Alpha Vantage**：免費版限流 5 req/min、500 req/day，6 檔資產可勉強完成但增加實作
  複雜度；且需 API key 註冊，違反「pip install 後即可跑」的 onboarding 預期。
- **Polygon.io / IEX Cloud**：付費，違反論文可重現性的「免註冊」原則。
- **FinRL 內建 `YahooDownloader`**：實質為 yfinance 包裝層，多一層相依無增益。

**Version pin strategy**：在 `pyproject.toml` 鎖定 `yfinance ~= 0.2.40`，
`requirements-lock.txt` 鎖至補丁版號（research R7 of 001 已建立此模式，002 沿用）。

---

## R2：FRED 利率資料源 client 選擇

**Decision**: 採用 `fredapi` ≥ 0.5.2，需要使用者於環境變數 `FRED_API_KEY` 提供註冊金鑰。

**Rationale**:
- FRED（Federal Reserve Economic Data）為聖路易聯儲免費公開資料庫，DTB3 為其
  3-month T-bill 標準序列，論文選作無風險利率代理。
- `fredapi` 為 St. Louis Fed 社群推薦之輕量 client，僅依賴 `requests` 與 `pandas`。
- API key 為免費註冊（https://fred.stlouisfed.org/docs/api/api_key.html），單一 key
  限額 120 req/min，本 feature 一次抓取僅 1 series，遠低於上限。

**Alternatives considered**:
- **`pandas-datareader`**：歷史包袱重、近年維護緩慢，FRED 端點偶有 breakage。
- **直接呼叫 FRED REST API**：技術可行但需自行處理 ETag、retry、JSON parsing；
  額外開發成本不抵省下的相依。
- **改用 ECB / OECD 資料**：違反 spec FR-025（資料源鎖定 yfinance + FRED）。

**Key handling**：
- 環境變數 `FRED_API_KEY` 是唯一傳遞方式；嚴禁出現於原始碼、commit、metadata。
- 若未設定，抓取指令於開始前即 fail-fast 並指引註冊流程（spec FR-021）。

---

## R3：重試與退避策略

**Decision**: 使用 `tenacity` ≥ 8.2 實作指數退避重試。針對 yfinance/fredapi 的
HTTP 暫時性錯誤（5xx、429、ConnectionError、Timeout）採 base=1s、multiplier=2、
max_attempt=5 的指數退避；對永久性錯誤（4xx 非 429、symbol 不存在、series 不存在）
立即 fail-fast 不重試。

**Rationale**:
- `tenacity` 為 Python 生態事實標準的重試函式庫，retry-on-exception、
  wait_exponential、stop_after_attempt 三個 decorator 即可組合所有需求。
- 5 次重試 + 指數退避（1s → 2s → 4s → 8s → 16s = 31s 總等待上限）可吸收常見的
  Yahoo / FRED 短暫服務波動，又不至於讓 SC-001（< 5 分鐘總耗時）失守。
- 4xx 立即 fail-fast 對齊 spec FR-020；symbol 退市等錯誤不應浪費重試額度。

**Alternatives considered**:
- **`urllib3.Retry`**：低階、僅作用於 requests 層，無法針對 yfinance 的高階例外
  分類重試；較適合 raw HTTP client。
- **`backoff` 套件**：功能近似 tenacity 但生態較小；無顯著優勢。
- **手寫 retry loop**：易遺漏 jitter、邊界條件，違反「可重現」精神。

**Determinism note**：tenacity 的 wait_exponential 不引入隨機 jitter（除非顯式啟用
`wait_random_exponential`）；本 feature **禁止 jitter**，以維持「相同網路條件下
重試時序一致」的弱可重現性。

---

## R4：Parquet 寫入 byte-determinism 策略

**Decision**: 使用 `pyarrow` ≥ 15.0 寫入 Parquet，固定下列參數確保跨平台 byte-identical：
- `compression="snappy"`（spec FR-004）
- `version="2.6"`（Parquet format version 鎖定）
- `data_page_version="2.0"`
- `write_statistics=False`（統計欄位含浮點 min/max，跨平台可能 byte 不同）
- `coerce_timestamps="us"` + `allow_truncated_timestamps=False`（時間戳精度鎖定為微秒）
- `created_by` 元資料欄位**不寫入**（pyarrow 會將套件版本字串嵌入檔頭，破壞跨版本
  byte-identical）；以 `kvmeta` 自訂欄位記錄。

**Rationale**:
- pyarrow 的 Parquet writer 預設會在檔頭嵌入 `pyarrow.__version__` 與 `created_by`
  字串，導致同一資料、不同 pyarrow 版本寫出的檔案 SHA-256 不同。固定 pyarrow 版本
  + 移除 created_by 是唯一可靠方法。
- snappy 壓縮為 deterministic 演算法（無亂數、無平台 SIMD 差異），跨平台一致。
- Parquet version 2.6 + data_page v2 為 pyarrow 15+ 推薦組合，與下游 pandas 完整相容。
- `write_statistics=False` 雖犧牲少量讀取效能（無 page-level 跳讀），但 SC-003
  要求載入 < 100 ms 仍可達成（檔案僅 ~500 列）；換取 byte-determinism 划算。

**Alternatives considered**:
- **fastparquet**：另一 Parquet 寫入器，但 pandas 內部優先呼叫 pyarrow；混用會導致
  下游讀取行為差異。pin pyarrow 為唯一寫入器更乾淨。
- **不要求 byte-identical，只要求邏輯一致**：違反 SC-007 與 spec FR-013（SHA-256
  對二進位內容計算，任何 byte 改動皆需偵測）。

**驗證計畫**：CI 矩陣（Linux / macOS / Windows）執行 fetch 後比對所有 Parquet 的
SHA-256；不一致即 fail。對應 tasks.md 的 cross-platform fixture 任務。

---

## R5：原子性寫入策略（all-or-nothing）

**Decision**: 採「temp directory + atomic rename」模式：
1. 抓取時先寫入 `data/raw/.staging-<timestamp>/` 暫存目錄。
2. 全部 7 個 Parquet + metadata 寫入成功後，逐檔 `os.replace()` 至 `data/raw/`
   覆寫舊檔（POSIX rename 為 atomic）。
3. 若任一抓取或寫入步驟失敗，刪除整個 staging 目錄、保留 `data/raw/` 舊版本不變、
   拋出明確錯誤（spec FR-018、SC-004）。

**Rationale**:
- 對應 spec User Story 3 Acceptance Scenario 2（重建中途失敗不留半完成檔案）與
  Edge Case「磁碟空間不足」「Windows 檔案佔用」。
- `os.replace()` 為跨平台 atomic 操作（Windows 與 POSIX 皆保證 single-file rename
  atomicity；目錄級 atomicity 透過「先全部成功才開始 rename」實現）。
- staging 目錄的時間戳後綴避免並行抓取（即使 spec 不支援並行，CI 上偶有殘留）的
  互相干擾。

**Alternatives considered**:
- **直接覆寫**：失敗時留下「部分新 + 部分舊」混合狀態，違反 SC-004。
- **整個 `data/raw/` 先複製為備份再覆寫**：磁碟用量翻倍、為小機率事件付出大成本，
  且仍需 atomic rename 才能保證一致性。
- **使用 SQLite 的 transaction**：本 feature 輸出為檔案不為 row，引入 RDBMS 過度。

**Windows 注意**：Windows 上若目標檔被其他進程鎖定（如 Excel 開啟 Parquet），
`os.replace()` 會 raise `PermissionError`；錯誤訊息需明確告知（spec Edge Case）。

---

## R6：SHA-256 計算與驗證流程

**Decision**:
- **計算**：以 64 KiB chunks 串流讀取 Parquet 二進位內容，餵入 `hashlib.sha256()`，
  輸出 64 字元 hex digest。對應 metadata 中 `sha256` 欄位。
- **驗證**：CLI `verify` 子指令掃描 `data/raw/*.parquet`，對每檔重算 SHA-256 並
  與 `<file>.parquet.meta.json` 中的 `sha256` 比對；不符或缺檔則 exit code != 0
  並列出細節（spec FR-015、FR-016、SC-002）。

**Rationale**:
- SHA-256 為密碼學雜湊，碰撞機率可忽略；對 byte-level 改動敏感，符合 FR-013。
- chunked read 避免大檔案爆記憶體（雖本 feature 檔案小，仍為良好實踐）。
- 驗證與抓取為**互不依賴的 CLI 子指令**，使下游 CI / git pre-commit hook 可獨立
  呼叫驗證而不觸發網路抓取（Principle I 的純檢查點）。

**Verification ordering**：先驗證 metadata 存在性 → 再驗 Parquet 存在性 → 最後比對
SHA-256；任一階段失敗立即報錯，不繼續後續比對。

---

## R7：套件版本鎖定策略

**Decision**:
- `pyproject.toml` 中以兼容範圍宣告主要相依：`yfinance~=0.2.40`、`fredapi~=0.5.2`、
  `pyarrow~=15.0`、`pandas>=2.0,<3.0`、`tenacity~=8.2`。
- `requirements-lock.txt` 由 `pip-compile`（pip-tools）生成，鎖定所有遞移相依至
  patch 版本，並 commit 至 repo。
- metadata JSON 的 `upstream_package_versions` 欄位於抓取當下從 `importlib.metadata`
  動態查詢並寫入；偵測到與 lock file 不符時警告但不 fail（允許開發者測試新版本）。

**Rationale**:
- 與 001 sub-feature 的 R7 共用同一鎖版策略（憲法 Principle I 一致性）。
- pip-tools 為事實標準、生成的 lock file 可手動審閱、相容 pip。
- 動態查詢版本而非 hardcoded：避免 lock file 與實際安裝版本飄移時 metadata 紀錄
  舊資訊。

**Alternatives considered**:
- **Poetry**：功能完整但引入額外工具鏈；本專案已決定使用 pip + pyproject.toml 平
  原生路徑（001 plan.md 已確立）。
- **conda-lock**：適合科學計算環境，但 yfinance 在 conda-forge 有時落後；維持 pip
  路徑更直接。

---

## R8：CLI 框架選擇

**Decision**: 使用 Python 標準函式庫 `argparse` 實作 CLI，不引入第三方 CLI 框架。

**Rationale**:
- 本 feature 僅三個子指令（`fetch`、`verify`、`rebuild`）與少量參數，argparse 足夠
  且零相依。
- 不引入 `click` 或 `typer` 可避免額外的 lock entries、減少 supply chain 表面。
- argparse 跨平台行為一致、help text 自動生成、type coercion 完整。

**Alternatives considered**:
- **`click`**：API 較友善但增加相依；對如此簡單的 CLI 過度。
- **`typer`**：基於 click + type hints，優雅但引入額外鏈式相依（pydantic 等）。

**Subcommand layout**：`python -m data_ingestion.cli {fetch|verify|rebuild}`，亦提供
`pyproject.toml` 的 `[project.scripts]` 註冊為 `ppo-smc-data` 短指令。

---

## R9：時間範圍與交易日邊界處理

**Decision**:
- 設定起訖日期皆為**含端點**（inclusive）。yfinance 的 `download(start, end)`
  end 為 exclusive；本 feature CLI 內部將 end 加 1 天再傳入，使對外語意與 spec
  FR-005 一致（2018-01-01 至 2026-04-29 含末日）。
- FRED 的 `get_series(observation_start, observation_end)` 預設 inclusive，無需轉換。
- 兩個資料源的 index 對齊到「該資料源回傳的交易日」，**不**強制 reindex 至共同
  日曆（DTB3 為每日銀行日，含部分非美股交易日；股票為 NYSE 交易日）。下游 feature
  自行 join。

**Rationale**:
- 不做 reindex 維持「資料原貌」（spec FR-010 不修補政策）。
- 端點包含/排除的細節若不文件化，下游將產生 off-by-one bug。
- 兩源日曆不同為金融資料常識，論文 reward 計算時依交易日 reindex DTB3 為標準做法。

---

## R10：metadata JSON Schema 嚴格度

**Decision**: 採用 JSON Schema Draft 2020-12 描述 metadata 結構，置於
`contracts/snapshot-metadata.schema.json`。驗證指令在比對 SHA-256 之前先以
`jsonschema` ≥ 4.20 驗證 metadata 檔結構合規；schema 不合規時報「metadata 損毀」。

**Rationale**:
- metadata 作為 002↔001 與 002↔CI 的契約點，schema-first 可阻擋手動誤改。
- `jsonschema` 為 PyPI 標準函式庫，輕量、跨平台、無原生相依。
- Draft 2020-12 為當前最新穩定版，支援 `unevaluatedProperties` 以禁止額外欄位
  滲入（避免使用者手寫 metadata 時偷渡未授權欄位）。

**Alternatives considered**:
- **Pydantic V2**：型別更嚴格但引入較大相依鏈；本 feature 不需 Pydantic 的
  serialization / settings 等功能。
- **手寫 dict 驗證**：易遺漏邊界、無法被 IDE 補全；違反「規格先行」精神。

---

## 決策匯總

| ID | 主題 | 決策 |
|----|------|------|
| R1 | 股票資料源 | yfinance ~= 0.2.40，auto_adjust=True |
| R2 | 利率資料源 | fredapi ~= 0.5.2，FRED_API_KEY 環境變數 |
| R3 | 重試策略 | tenacity ~= 8.2，指數退避 5 次、無 jitter |
| R4 | Parquet 寫入 | pyarrow ~= 15.0，snappy + version 2.6 + 移除 created_by |
| R5 | 原子性寫入 | staging dir + os.replace() |
| R6 | SHA-256 | hashlib chunked + 獨立 verify CLI |
| R7 | 版本鎖定 | pyproject.toml 範圍 + requirements-lock.txt 精確 |
| R8 | CLI 框架 | argparse（標準函式庫） |
| R9 | 時間端點 | inclusive 兩端，內部對 yfinance end+1 |
| R10 | metadata schema | JSON Schema Draft 2020-12 + jsonschema 套件 |

**全部 NEEDS CLARIFICATION 已解決**，可進入 Phase 1。
