# CLI Contract: 002-data-ingestion

**Date**: 2026-04-29
**Status**: Phase 1 contract — implementation MUST adhere to this signature.

本文件定義 002 feature 對外暴露的 CLI 介面。所有指令的退出代碼、stdout 格式、
stderr 格式、與例外處理為下游 CI / 使用者所依賴的契約點，變更需 PR 審查。

進入點：

- `python -m data_ingestion.cli ...`（總是可用）
- `ppo-smc-data ...`（透過 `pyproject.toml` `[project.scripts]` 註冊的短指令）

兩個進入點 100% 等價。本文件以後者示範。

---

## 全域選項

| 選項 | 簡稱 | 預設 | 說明 |
|------|------|------|------|
| `--config PATH` | `-c` | （內建預設） | 指向自訂 ingestion config 的 TOML/JSON 檔（覆寫預設） |
| `--output-dir PATH` | `-o` | `data/raw` | 輸出目錄 |
| `--log-level LEVEL` | | `INFO` | 列舉：`DEBUG`、`INFO`、`WARNING`、`ERROR` |
| `--help` | `-h` | | 顯示說明並退出 |
| `--version` | | | 顯示套件版本並退出 |

---

## Subcommand: `fetch`

**用途**：從零或既有狀態抓取全部 7 個快照（6 OHLCV + 1 利率）。User Story 1。

**完整語法**：

```bash
ppo-smc-data fetch [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--dry-run]
```

**選項**：

| 選項 | 預設 | 說明 |
|------|------|------|
| `--start YYYY-MM-DD` | `2018-01-01` | 抓取起始日（含） |
| `--end YYYY-MM-DD` | `2026-04-29` | 抓取結束日（含） |
| `--dry-run` | False | 僅檢查設定與環境變數，不發起網路請求 |

**前置條件**：

- 環境變數 `FRED_API_KEY` MUST 已設定（否則立即 fail-fast，退出代碼 2）。
- 網路可達 `query2.finance.yahoo.com` 與 `api.stlouisfed.org`。

**行為**：

1. 驗證 IngestionConfig（spec FR-005、§5 data-model.md）。
2. 建立 staging 目錄 `data/raw/.staging-<UTC_YYYYMMDDHHMMSS>/`。
3. 對 6 檔股票/ETF 依序呼叫 yfinance（research R3 重試策略）。
4. 對 DTB3 呼叫 fredapi。
5. 對每個資料應用 quality_flag 處理（data-model.md §4）。
6. 寫入 staging 目錄為 Parquet（research R4 byte-determinism 設定）。
7. 計算 SHA-256、寫入 metadata JSON（schema 見 `snapshot-metadata.schema.json`）。
8. 全部成功後逐檔 `os.replace()` 移至 `data/raw/`，並刪除 staging 目錄。
9. 輸出每檔的 SHA-256 與檔名摘要。

**stdout 格式**（成功）：

```text
[fetch] Starting ingestion: 2018-01-01 → 2026-04-29
[fetch] yfinance: NVDA ... ok (2087 rows, sha256=e3b0c44...)
[fetch] yfinance: AMD  ... ok (2087 rows, sha256=12ab34c...)
...
[fetch] fred: DTB3    ... ok (2168 rows, sha256=89ef01a...)
[fetch] All 7 snapshots written to data/raw/ in 47.3s
```

**退出代碼**：

| Code | 含義 |
|------|------|
| 0 | 全部 7 個快照寫入成功 |
| 1 | 抓取或寫入失敗（任一資產失敗皆此代碼，staging 已清除） |
| 2 | 設定錯誤（缺 FRED_API_KEY、日期非法、output_dir 不可寫） |
| 130 | 使用者中斷（Ctrl+C） |

**錯誤訊息範例**（spec FR-021 直接判讀）：

```text
[fetch] ERROR: Failed to download yfinance ticker 'TSM' after 5 retries.
        Last error: yfinance.exceptions.YFTzMissingError
        Hint: ticker may be delisted or temporarily unavailable.
        Staging directory data/raw/.staging-20260429-031415/ has been cleaned up.
        data/raw/ is unchanged.
Exit code: 1
```

---

## Subcommand: `verify`

**用途**：驗證 `data/raw/` 中所有快照的 SHA-256 與 metadata 完整性。User Story 2。

**完整語法**：

```bash
ppo-smc-data verify [--strict]
```

**選項**：

| 選項 | 預設 | 說明 |
|------|------|------|
| `--strict` | False | 啟用嚴格模式：未在預期清單中的 .parquet 檔也視為錯誤 |

**前置條件**：無（純本地檢查、不需網路、不需 FRED_API_KEY）。

**行為**：

1. 列舉 `data/raw/*.parquet` 與對應 `*.parquet.meta.json`。
2. 對每個 metadata 執行 JSON Schema 驗證（research R10）。
3. 對每個 Parquet 重算 SHA-256，與 metadata 中的 `sha256` 比對。
4. 比對 `row_count`、`column_schema`、`index_schema` 與 Parquet 實際結構。
5. 列出所有 mismatch 與 missing。

**stdout 格式**（全綠）：

```text
[verify] Scanning data/raw/ ...
[verify] nvda_daily_20180101_20260429.parquet  OK  (sha256=e3b0c44...)
[verify] amd_daily_20180101_20260429.parquet   OK  (sha256=12ab34c...)
...
[verify] dtb3_daily_20180101_20260429.parquet  OK  (sha256=89ef01a...)
[verify] All 7 snapshots verified successfully.
```

**stdout 格式**（有錯）：

```text
[verify] nvda_daily_20180101_20260429.parquet  FAIL
         Expected sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
         Actual sha256:   d72f819a3...
[verify] tlt_daily_20180101_20260429.parquet   MISSING
         metadata exists but Parquet file not found.
[verify] 2 snapshot(s) failed verification. See above.
```

**退出代碼**：

| Code | 含義 |
|------|------|
| 0 | 全部 metadata + Parquet 皆通過 |
| 1 | 至少一個快照 SHA-256 不符或 metadata schema 不合規 |
| 2 | `data/raw/` 不存在或無讀取權限 |
| 3 | 使用 `--strict` 時偵測到非預期檔案 |

---

## Subcommand: `rebuild`

**用途**：強制覆寫既有快照（即使 SHA-256 通過）。User Story 3。

**完整語法**：

```bash
ppo-smc-data rebuild [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--yes]
```

**選項**：

| 選項 | 預設 | 說明 |
|------|------|------|
| `--start YYYY-MM-DD` | （讀取既有 metadata） | 新起始日 |
| `--end YYYY-MM-DD` | （讀取既有 metadata） | 新結束日 |
| `--yes` | False | 跳過互動式確認；CI 必填 |

**行為**：

1. 若無 `--yes`：讀取既有 metadata，列印「即將覆寫的檔名 + 預期新範圍」並要求 `y/N`。
2. 等同 `fetch`，但忽略既有 `data/raw/` 中的 SHA-256（仍走 staging + atomic rename）。
3. 若任一抓取失敗，**完全保留**舊版本（spec User Story 3 Acceptance Scenario 2）。

**退出代碼**：與 `fetch` 相同。

---

## 公開 Python API（下游 feature 載入快照）

下游（特別是 001-smc-feature-engine）載入快照無需透過 CLI。提供下列 Python 公開
API 供程式內呼叫：

完整 type stub 見 `contracts/api.pyi`。摘要：

```python
def load_asset_snapshot(ticker: str, data_dir: Path = Path("data/raw")) -> pd.DataFrame: ...
def load_rate_snapshot(series_id: str = "DTB3", data_dir: Path = Path("data/raw")) -> pd.DataFrame: ...
def load_metadata(parquet_path: Path) -> SnapshotMetadata: ...
def verify_snapshot(parquet_path: Path) -> VerifyResult: ...
```

User Story 4 的 Acceptance Scenario 1（< 100 ms 載入）由 `load_asset_snapshot` 保證。

---

## 不變式

1. **退出代碼穩定**：上述代碼變更為 BREAKING change，需 MAJOR feature bump。
2. **stdout 格式為非結構化人類可讀**；CI 應依退出代碼判斷成敗，而非 parse stdout。
3. **stderr 僅用於 logging（依 `--log-level`）與致命錯誤訊息**；不混雜 stdout。
4. **無互動模式預設**：除 `rebuild` 無 `--yes` 之外，所有指令在非 TTY 環境（CI）
   皆能直接執行不卡 stdin。
5. **可重入**：`fetch` 與 `verify` 連續多次執行結果一致（相同網路條件下）；
   `rebuild` 連續執行第二次起若 `--start/--end` 未變則為 no-op 等價於 fetch。
