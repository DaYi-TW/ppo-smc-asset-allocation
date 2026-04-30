---

description: "Task list for 002-data-ingestion implementation"
---

# Tasks: 002-data-ingestion

**Input**: Design documents from `/specs/002-data-ingestion/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/{cli.md,snapshot-metadata.schema.json,api.pyi}

**Tests**: Tests are REQUIRED for this feature — sec SC-002（驗證機制）、SC-003
（< 100 ms 載入）、SC-004（原子性）、SC-007（byte-identical）皆需測試覆蓋；coverage
≥ 90% 為憲法 Principle I 的可重現性硬要求。

**Organization**: 任務依 user story（US1–US4）分組以利獨立實作與測試；Setup 與
Foundational 為共同前置；Polish 為跨 story 收尾。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依）
- **[Story]**：所屬 user story（US1 / US2 / US3 / US4 / —為 Setup/Foundational/Polish）
- 描述含實際檔案路徑（依 plan.md Project Structure）

## Path Conventions

採 **Single project monorepo**：

- 原始碼：`src/data_ingestion/`
- 測試：`tests/{contract,integration,unit}/`
- 資料輸出：`data/raw/`（commit 進 repo，憲法 Principle I 載體）
- 與 001 共用 `pyproject.toml` 與 `requirements-lock.txt`

---

## Phase 1: Setup（Shared Infrastructure）

**Purpose**：建立 002 package 結構、Docker 開發環境、相依管理；多數結構已被 001 plan
預先規劃，本 phase 補上 002 專屬內容與整體 Docker 化。

- [x] **T000a** 在 repo 根目錄建立 `Dockerfile`（基底 `python:3.11-slim`、non-root user
  `dev` uid=1000、`WORKDIR /workspace`、安裝 build 工具供 pyarrow wheel fallback、
  `pip install -e . -r requirements-lock.txt`）
- [x] **T000b** 在 repo 根目錄建立 `docker-compose.yml`（service `dev`：bind mount
  `.:/workspace`、`env_file: .env`、`tty: true`、`stdin_open: true`、預設 cmd `bash`）
- [x] **T000c** 在 repo 根目錄建立 `.dockerignore`（排除 `.git/`、`.venv/`、`.pytest_cache/`、
  `__pycache__/`、`.env`、`data/raw/.staging-*/`；保留 `data/raw/*.parquet*` 因為 build
  context 不該帶大量資料但 mount 後可見）
- [x] **T000d** 確認 repo 根目錄 `.gitignore` 已含 `.env`（若無則補上）；確保 `.env.example`
  已 commit 為使用者範本（已存在於前置 commit）
- [x] **T001** 建立 `src/data_ingestion/` package 目錄與空 `__init__.py`；同時建立
  `src/data_ingestion/sources/` 子套件目錄與空 `__init__.py`
- [x] **T002** 在 repo 根目錄的 `pyproject.toml` 新增 002 相依（`yfinance~=0.2.40`、
  `fredapi~=0.5.2`、`tenacity~=8.2`、`jsonschema>=4.20`），確認既有 001 相依不衝突
- [x] **T003** 在 `pyproject.toml` 的 `[project.scripts]` 新增 `ppo-smc-data =
  "data_ingestion.cli:main"` 進入點
- [x] **T004** 執行 `pip-compile` 更新 `requirements-lock.txt`，確認 yfinance /
  fredapi / pyarrow / pandas 的 patch 版本鎖定（research R7）；commit lock file
- [x] **T005** [P] 建立 `data/raw/.gitkeep` 並新增 `data/raw/.staging-*/` 至
  `.gitignore`（避免暫存目錄被誤 commit）
- [x] **T006** [P] 在 CI 設定（GitHub Actions YAML）新增 `ppo-smc-data verify` 步驟
  的 placeholder（實際指令於 US2 任務後啟用）

**Checkpoint**：
- `docker compose build dev` 成功（image 大小 < 600 MB）
- `docker compose run --rm dev python -c "import data_ingestion"` 通過（雖然空 module）
- `docker compose run --rm dev ppo-smc-data --help` 可呼叫但回應「not implemented」

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：所有 user story 共用的核心型別、配置、工具函式；US1–US4 任一啟動皆需
本 phase 完成。

**⚠️ CRITICAL**：US1–US4 不得在 Phase 2 完成前開始。

- [x] **T007** 在 `src/data_ingestion/config.py` 實作 `IngestionConfig`
  frozen dataclass + 驗證邏輯（data-model.md §5；違規拋 `ValueError`）
- [x] **T008** [P] 在 `src/data_ingestion/quality.py` 實作 `quality_flag` 列舉常數
  與判定函式（data-model.md §4 五個值 + 優先序）
- [x] **T009** [P] 在 `src/data_ingestion/hashing.py` 實作 `sha256_of_file()`
  使用 64 KiB chunked read（research R6）
- [x] **T010** [P] 在 `src/data_ingestion/atomic.py` 實作 staging dir 建立、
  全部完成後逐檔 `os.replace()` 遷移、失敗時清理（research R5）；含 Windows
  `PermissionError` 友善訊息
- [x] **T011** 在 `src/data_ingestion/__init__.py` re-export contracts/api.pyi
  列出的所有公開符號（先建立可 import 的空 stub，逐步替換為真實實作）
- [x] **T012** [P] [US1+US2] 撰寫 `tests/contract/test_public_api.py` —
  以 `inspect.signature` 驗證 `__init__.py` 暴露的符號集合與簽章與 contracts/api.pyi
  完全一致；初始 RED（先有空 stub 應通過簽章測試）
- [x] **T013** [P] [US2] 撰寫 `tests/contract/test_metadata_schema.py` —
  讀取 `contracts/snapshot-metadata.schema.json`，以 jsonschema 套件驗證一個合法
  metadata 範例通過、各種違規範例失敗（schema_version 錯、sha256 大小寫、
  unevaluatedProperties 等）
- [x] **T014** [P] [US1] 撰寫 `tests/contract/test_cli_exit_codes.py` —
  使用 `subprocess.run` 呼叫 `ppo-smc-data {fetch,verify,rebuild} --help`，
  斷言 help 輸出含關鍵子指令名與必要選項；簽章層級的 RED 測試

**Checkpoint**：`pytest tests/contract/` 通過簽章與 schema 層級檢查（實作層仍未
完成，整合測試應 fail）。所有公開 API 符號可被 import。

---

## Phase 3: User Story 1 — 研究者一次性建立可重現資料快照（P1） 🎯 MVP

**Goal**：交付 `ppo-smc-data fetch` 指令，從零產出 7 個 Parquet + 7 個 metadata
JSON 至 `data/raw/`，於 < 5 分鐘完成（SC-001）。

**Independent Test**：在乾淨環境執行 `ppo-smc-data fetch`，驗證 14 個檔案產出且
能被 `pd.read_parquet` 讀回；隨機抽兩檔比對欄位、列數、時間範圍符合 spec。

### Tests for User Story 1（先寫測試，先 RED）

- [x] **T015** [P] [US1] `tests/unit/test_config.py` — `IngestionConfig` 邊界值：
  非法日期、start > end、空 ticker、output_dir 型別錯誤皆拋 `ValueError`；正常
  建構回傳 frozen instance
- [x] **T016** [P] [US1] `tests/unit/test_quality.py` — quality_flag 判定：
  完整列為 `ok`、close=NaN 為 `missing_close`、volume=0 為 `zero_volume`、
  rate=NaN 為 `missing_rate`；多條件同列依優先序判定（data-model.md §4）
- [x] **T017** [P] [US1] `tests/unit/test_writer_determinism.py` — 對相同
  DataFrame 連續呼叫 `write_parquet()` 兩次，比對兩檔 SHA-256 byte-identical
  （research R4 鎖定設定生效）
- [x] **T018** [P] [US1] `tests/unit/test_hashing.py` — chunked SHA-256 對小、
  中、大三個檔案（< 64 KiB / 1 MiB / 10 MiB）結果與 `hashlib.file_digest` 相符
- [x] **T019** [P] [US1] `tests/unit/test_metadata.py` — metadata 物件序列化為
  JSON 後通過 schema 驗證；`upstream_package_versions` 由 `importlib.metadata`
  動態查詢；`fetch_timestamp_utc` 為 UTC + Z 後綴
- [x] **T020** [P] [US1] `tests/integration/test_atomic_fetch.py` —
  以 `monkeypatch` 攔截第 3 檔抓取拋例外，驗證 `data/raw/` 不變、staging 目錄
  被清除（FR-018、SC-004）；正常路徑則驗證 14 個檔案皆於 `data/raw/`、無殘留
  staging
- [x] **T021** [US1] `tests/integration/test_fetch_e2e.py` — 使用 vcrpy 或預錄
  的 yfinance/FRED 回應 cassette，端對端執行 `cli.fetch`；驗證 7 個 Parquet
  + 7 個 metadata 產出、quality_summary 對應實際資料、列數合理（NVDA 在 2018-01-01
  至 2026-04-29 約 2,087 列）

### Implementation for User Story 1

- [x] **T022** [US1] 在 `src/data_ingestion/sources/yfinance_source.py` 實作
  `fetch_yfinance(ticker, start, end, config)` — 呼叫 `yfinance.Ticker.history`
  或 `yfinance.download`、套用 tenacity 指數退避（research R3 無 jitter）、
  4xx 立即 fail-fast、回傳 `RawAssetData`（data-model.md §6.1）
- [x] **T023** [US1] 在 `src/data_ingestion/sources/fred_source.py` 實作
  `fetch_fred(series_id, start, end, config)` — 由環境變數讀取 `FRED_API_KEY`、
  缺失時 fail-fast 並指引註冊流程（FR-021）；同樣套用 tenacity 重試；回傳
  `RawRateData`
- [x] **T024** [US1] 在 `src/data_ingestion/quality.py` 補上 `apply_quality_flags(df)`
  函式 — 偵測重複 timestamp 保留首次、產出 `quality_flag` 欄、回傳 `(clean_df,
  duplicate_dropped_timestamps)` tuple（FR-011）
- [x] **T025** [US1] 在 `src/data_ingestion/writer.py` 實作
  `write_parquet(df, path, config)` — 使用 pyarrow Table，鎖定參數
  `compression="snappy"`、`version="2.6"`、`data_page_version="2.0"`、
  `write_statistics=False`、移除 `created_by` 元資料（research R4）
- [x] **T026** [US1] 在 `src/data_ingestion/metadata.py` 實作
  `build_metadata(...)` 與 `write_metadata_json(meta, path)` — 動態查詢
  `importlib.metadata.version()`、寫入 JSON 前以 jsonschema 自驗（research R10）；
  時間戳以 `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` 產生（FR-014）
- [x] **T027** [US1] 在 `src/data_ingestion/atomic.py` 補上
  `atomic_publish(staging_dir, target_dir)` — 全部成功後逐檔 `os.replace()`、
  最後刪除 staging；任何例外則整個 staging 移除並 reraise
- [x] **T028** [US1] 在 `src/data_ingestion/cli.py` 實作 argparse 結構與
  `cmd_fetch(args, config)` — 串接 sources → quality → writer → metadata →
  atomic_publish；stdout 採 contracts/cli.md 規定格式；退出代碼 0 / 1 / 2 / 130
  對應規格
- [x] **T029** [US1] 在 `src/data_ingestion/cli.py` 補上 `main()` 函式
  作為 `[project.scripts]` 進入點；處理 `KeyboardInterrupt` → exit 130

**Checkpoint**：`ppo-smc-data fetch` 在乾淨環境可成功產出 14 個檔案；
`pytest tests/integration/test_fetch_e2e.py` 與 `tests/integration/test_atomic_fetch.py`
通過；`pytest tests/unit/` 全綠。MVP 達標。

---

## Phase 4: User Story 2 — 任何使用者驗證本地快照未被竄改（P2）

**Goal**：交付 `ppo-smc-data verify` 指令與 Python `verify_snapshot` API，純本地
比對 SHA-256 與 metadata，提供 SC-002 的「全綠 / 精確失敗」二態結果。

**Independent Test**：對 US1 產出的 `data/raw/` 執行 `ppo-smc-data verify` →
exit 0；手動修改任一 Parquet 一個 byte → exit != 0 且訊息含檔名與雜湊細節。

### Tests for User Story 2

- [x] **T030** [P] [US2] `tests/unit/test_loader.py` — `load_metadata()`
  對合法 / 違反 schema / 缺欄位三種情境分別正常返回 / 拋 `ValueError`；
  `load_asset_snapshot()` 對缺檔拋 `FileNotFoundError`、對歧義（同 ticker 多檔）
  拋 `ValueError`
- [x] **T031** [P] [US2] `tests/integration/test_verify_roundtrip.py` —
  fetch → verify 路徑全綠；對 staging 中任一 Parquet 末尾追加 1 byte 後再 verify，
  斷言失敗訊息含該檔名、預期雜湊、實際雜湊（FR-016）；缺檔情境亦覆蓋
- [x] **T032** [P] [US2] `tests/contract/test_cli_exit_codes.py` 補充：
  `verify` 退出代碼 0 / 1 / 2 / 3（`--strict` 模式偵測非預期檔案）覆蓋

### Implementation for User Story 2

- [x] **T033** [US2] 在 `src/data_ingestion/loader.py` 實作 `load_metadata(path)`
  — 讀取 `*.parquet.meta.json`、執行 jsonschema 驗證、parse 為
  `SnapshotMetadata` frozen dataclass（contracts/api.pyi）
- [x] **T034** [US2] 在 `src/data_ingestion/verify.py` 實作 `verify_snapshot(path)`
  與 `verify_all(data_dir)` — 重算 SHA-256、比對 metadata 中的 `sha256`、
  `row_count`、`column_schema` 與 Parquet 實際 schema；回傳 `VerifyResult`
- [x] **T035** [US2] 在 `src/data_ingestion/cli.py` 補上 `cmd_verify(args)` —
  呼叫 `verify_all`、依 contracts/cli.md 格式輸出每檔狀態、exit code 對齊
  契約；`--strict` 模式偵測 `data/raw/*.parquet` 中不在預期清單的檔案
- [x] **T036** [US2] 啟用 T006 的 CI verify 步驟（將 placeholder 替換為
  `ppo-smc-data verify`），確認 CI 在 commit 含 `data/raw/` 時自動驗證

**Checkpoint**：US1 與 US2 並用：`ppo-smc-data fetch && ppo-smc-data verify`
全綠；CI 上 verify 步驟可獨立通過（不需 FRED_API_KEY、不需網路）。

---

## Phase 5: User Story 3 — 研究者擴展時間範圍重建快照（P3）

**Goal**：交付 `ppo-smc-data rebuild` 指令，安全覆寫既有快照（保留舊版直至新版
全部成功），含互動式確認（CI 以 `--yes` 跳過）。

**Independent Test**：在已有 `data/raw/` 的環境執行 `rebuild --start 2015-01-01
--yes`，驗證所有 Parquet 被覆寫、新 metadata 的 call_params.start 為 `2015-01-01`、
列數較舊版多；中途模擬失敗時舊版完整保留。

### Tests for User Story 3

- [x] **T037** [P] [US3] `tests/integration/test_rebuild_atomicity.py` —
  以既有 `data/raw/` 為起點，monkeypatch 第 5 檔抓取失敗，驗證
  rebuild 後 `data/raw/` 仍為原版（檔名、SHA-256 不變）；正常路徑則驗證新版
  覆寫成功且舊版完全消失
- [x] **T038** [P] [US3] `tests/contract/test_cli_exit_codes.py` 補充：
  `rebuild --yes` 不卡 stdin；無 `--yes` 時模擬 stdin `n\n` → exit 0 不執行；
  `y\n` → 進入 fetch 流程

### Implementation for User Story 3

- [x] **T039** [US3] 在 `src/data_ingestion/cli.py` 補上 `cmd_rebuild(args)` —
  讀取既有 metadata 列出將被覆寫的檔名、若無 `--yes` 則互動式確認；底層共用
  `cmd_fetch` 的 staging + atomic_publish 流程
- [x] **T040** [US3] 在 `cmd_rebuild` 中實作 `--start` / `--end` 覆寫
  既有 metadata 中的 `data_source_call_params`；若使用者未提供任一參數，
  從現有 metadata 推斷預設值

**Checkpoint**：rebuild 可擴展或縮減時間範圍；中途失敗保留舊版（SC-004 跨抓取/
重建一致）。

---

## Phase 6: User Story 4 — 下游 feature 載入快照進行特徵計算（P2）

**Goal**：保證 `load_asset_snapshot` 與 `load_rate_snapshot` 在 SSD 上 < 100 ms
（SC-003），且輸出 DataFrame 直接符合 001 spec 的輸入 schema 無需轉換。

**Independent Test**：6 行 Python 腳本：`load_asset_snapshot("NVDA")` → 量測
`time.perf_counter()` 差值 < 100 ms；`df.dtypes` 符合 contracts/api.pyi 規定
dtypes（open/high/low/close 為 float64、volume 為 int64、quality_flag 為 string）。

### Tests for User Story 4

- [x] **T041** [P] [US4] `tests/integration/test_load_perf.py` — 對既有
  `data/raw/nvda_daily_*.parquet` 連續呼叫 `load_asset_snapshot("NVDA")`
  10 次，p95 < 100 ms（SC-003）；CI 上以較寬鬆 < 500 ms 容忍 runner 變異
- [x] **T042** [P] [US4] `tests/integration/test_load_schema_compat.py` —
  載入後 DataFrame 的 dtypes、index 名稱、index dtype 與 001 spec 的
  data-model.md §1（OHLCV input schema）完全相符；可作為 `smc_features.batch_compute`
  的輸入而不需任何轉換
- [x] **T043** [P] [US4] 補強 `tests/unit/test_loader.py`：ticker 大小寫
  insensitive（`load_asset_snapshot("nvda")` 與 `"NVDA"` 等價）；data_dir
  非預設值亦正常載入

### Implementation for User Story 4

- [x] **T044** [US4] 在 `src/data_ingestion/loader.py` 實作
  `load_asset_snapshot(ticker, data_dir)` — 以 glob 找到匹配檔案、`pd.read_parquet`
  載入、檢查 dtype 符合 contract、回傳 DataFrame；ticker 自動 upper-case
- [x] **T045** [US4] 同檔實作 `load_rate_snapshot(series_id, data_dir)` —
  類似邏輯但回傳 `rate_pct` + `quality_flag` 兩欄
- [x] **T046** [US4] 在 `src/data_ingestion/__init__.py` 確認
  `load_asset_snapshot` / `load_rate_snapshot` / `load_metadata` /
  `verify_snapshot` / `verify_all` 與 dataclass 全部於頂層可 import

**Checkpoint**：001 的 quickstart.md 範例（`from data_ingestion import
load_asset_snapshot; nvda = load_asset_snapshot("NVDA"); batch_compute(nvda, ...)`）
端對端跑通。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**：跨 user story 的收尾工作 — 文件、覆蓋率、跨平台驗證、品質工具。

- [x] **T047** [P] 設定 `ruff` 與 `mypy --strict` 於 `pyproject.toml` `[tool.*]`
  區段；新增 `pre-commit-config.yaml` 在 commit 前執行（與 001 共用設定）
- [x] **T048** [P] 撰寫 `tests/integration/test_cross_platform_fixture.py` —
  讀取 commit 進 repo 的 `tests/fixtures/golden_snapshots/` 中的小型參考 Parquet
  + metadata（事先在 Linux 上產生），於當前平台重算 SHA-256 並比對；CI 矩陣
  在 macOS / Windows 上執行此測試以證明 SC-007 跨平台 byte-identical
- [x] **T049** [P] 建立 `tests/fixtures/golden_snapshots/` 包含小型（~30 列）
  reference Parquet + metadata，commit 進 repo（≪ 1 MB）；T048 依賴此 fixture
- [x] **T050** 執行 `pytest --cov=data_ingestion --cov-report=term-missing` 並
  補上覆蓋未達 90% 的單元測試；SC-002/SC-003/SC-004/SC-007 路徑必須 100% 覆蓋
- [x] **T051** [P] 在 `tests/integration/test_error_messages.py` 驗證 SC-006：
  三種典型錯誤（symbol 退市、網路斷線、FRED 序列不存在）的 stderr 訊息含足夠
  上下文（ticker / URL / 修復提示），不僅顯示 stack trace
- [x] **T052** [P] 撰寫 `tests/integration/test_fetch_perf.py` — 使用 cassette
  模擬無延遲回應，量測 fetch 流程純本地時間 < 30 秒；SC-001 的 5 分鐘預算扣除
  網路時間後仍寬鬆
- [x] **T052a** [P] 撰寫 `tests/integration/test_repo_size.py` — 對 `data/raw/`
  下所有 `*.parquet` 與 `*.parquet.meta.json` 統計總位元組，斷言總和 < 10 MB
  （SC-005，控制 git clone 體積）；於 CI 上每次 commit data/raw/ 後執行
- [x] **T053** [P] 補強 README.md 增加 002 章節：「資料快照」段落引用
  `specs/002-data-ingestion/quickstart.md`
- [ ] **T054** 執行 quickstart.md §1–§7 全部步驟一次（人工驗證），確認新成員可
  在 5 分鐘內跑通；於 quickstart.md 末尾添加「驗證日期：YYYY-MM-DD」紀錄
- [ ] **T055** [P] 執行第一次正式 fetch 抓取真實資料，commit `data/raw/` 全部
  14 個檔案進 repo（這是 002 feature 的物理交付物，憲法 Principle I 載體）
- [ ] **T056** 在 PR 描述中附上 `ppo-smc-data verify` 的全綠輸出截圖；
  關閉 002-data-ingestion 對應的 spec review gate

**Checkpoint**：覆蓋率 ≥ 90%；CI 矩陣（Linux / macOS / Windows × Python 3.11 /
3.12）全綠；`data/raw/` 已 commit；下游 001 可立即進入 `/speckit.implement`。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**：無相依，可立即開始
- **Phase 2（Foundational）**：依賴 Phase 1 完成 — **BLOCKS** 所有 user story
- **Phase 3（US1 P1）**：依賴 Phase 2 — MVP 路徑
- **Phase 4（US2 P2）**：依賴 Phase 2；可與 US3 / US4 並行
- **Phase 5（US3 P3）**：依賴 Phase 2 + Phase 3 的 fetch / staging 程式碼
- **Phase 6（US4 P2）**：依賴 Phase 2；US4 可與 US2 並行（不同檔案）
- **Phase 7（Polish）**：依賴所有 user story 完成 — 含 T055 真實資料 commit

### User Story Dependencies

- **US1 → US2 / US3 / US4**：US2 / US4 需要 US1 已產出的 Parquet/metadata 才能
  做端對端測試（單元測試可使用 fixture 早期執行）；US3 直接 reuse US1 的
  fetch 流程
- **US2 ⫫ US4**：完全獨立檔案、可並行（不同開發者）

### Within Each User Story

- 測試（T012/T013/T014, T015–T021, T030–T032, T037–T038, T041–T043）MUST
  先寫且 RED 後再進入實作
- 公開 API stubs（T011）先於實作以利 contract test
- 模組分離原則：sources（抓取）→ quality（標籤）→ writer（Parquet）→
  metadata（JSON）→ atomic（rename）→ cli（組裝），相依鏈嚴格單向

### Parallel Opportunities

- Phase 1 標 [P] 任務（T005, T006）可同時執行
- Phase 2 標 [P] 任務（T008, T009, T010, T012, T013, T014）可並行 — 不同檔案
- Phase 3 測試任務 T015–T020 全部 [P] — 不同 test file
- Phase 4 / Phase 5 / Phase 6 可三組並行（不同 user story、不同檔案）
- Phase 7 多數 [P] — 文件、CI 設定、fixture 互不衝突

---

## Parallel Example: User Story 1 testing 階段

```bash
# Phase 3 RED tests，可平行寫入：
Task: "tests/unit/test_config.py — IngestionConfig 邊界值"
Task: "tests/unit/test_quality.py — quality_flag 列舉判定"
Task: "tests/unit/test_writer_determinism.py — 連續寫入 byte-identical"
Task: "tests/unit/test_hashing.py — chunked SHA-256"
Task: "tests/unit/test_metadata.py — metadata 序列化 + schema 驗證"
Task: "tests/integration/test_atomic_fetch.py — staging + rename 原子性"
```

---

## Implementation Strategy

### MVP First（US1 Only）

1. Phase 1（Setup）→ Phase 2（Foundational）→ Phase 3（US1）
2. **STOP & VALIDATE**：`ppo-smc-data fetch` 在乾淨環境跑通、`tests/integration/`
   US1 任務全綠
3. 此時已可產出 7 個快照；US2 / US3 / US4 可分批加入

### Incremental Delivery

1. Phase 1 + 2 → 基礎就緒
2. Phase 3（US1）→ 抓取能力（MVP）
3. Phase 4（US2）→ 驗證能力（憲法 Principle I 最後一塊）
4. Phase 6（US4）→ 下游消費能力（解鎖 001 implement）
5. Phase 5（US3）→ 重建能力（時間範圍擴展時才需要）
6. Phase 7（Polish）→ 收尾、cross-platform CI、commit data/raw/

### Parallel Team Strategy

- 一人專責 Setup + Foundational
- US1 由一人主導（測試 + 實作鏈最長）
- US2 / US3 / US4 在 US1 達 checkpoint 後可分配給三人並行

---

## Notes

- [P] 任務 = 不同檔案、無相依
- [Story] 標籤對應到 spec.md 的 user story 優先序
- 測試先行：每個 user story 內的測試任務 ID 皆早於對應實作任務
- 每完成一個任務即 commit（憲法 Development Workflow 第 6 步）
- T055（commit 真實 data/raw/）是 002 feature 的物理交付里程碑；
  T056 完成後 002 feature done，可正式啟動 `/speckit.implement` for 001
