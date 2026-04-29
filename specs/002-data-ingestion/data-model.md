# Phase 1 Data Model: 002-data-ingestion

**Date**: 2026-04-29
**Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md)
**Plan**: [plan.md](./plan.md)

定義本 feature 涉及的所有資料結構：Parquet 輸出 schema、metadata JSON schema、
設定物件、Quality Flag 列舉、不變式。所有結構為實作指引，最終以 Python type stubs、
dataclass 與 JSON Schema 具體化。

---

## 1. Asset Snapshot Parquet Schema

**用途**：6 檔股票/ETF（NVDA, AMD, TSM, MU, GLD, TLT）的 OHLCV 日線快照輸出。

**檔名**：`<ticker_lower>_daily_<startYYYYMMDD>_<endYYYYMMDD>.parquet`
（例：`nvda_daily_20180101_20260429.parquet`）

| 欄位 | dtype | 必要 | 值域 | 說明 |
|---|---|---|---|---|
| `open` | `float64` | ✅ | (0, ∞) ∪ {NaN} | 開盤價，已除權息調整（auto_adjust=True） |
| `high` | `float64` | ✅ | (0, ∞) ∪ {NaN} | 最高價，已除權息調整 |
| `low` | `float64` | ✅ | (0, ∞) ∪ {NaN} | 最低價，已除權息調整 |
| `close` | `float64` | ✅ | (0, ∞) ∪ {NaN} | 收盤價，已除權息調整 |
| `volume` | `int64` | ✅ | [0, ∞) | 成交量；零值代表停牌或未成交 |
| `quality_flag` | `string`（pyarrow utf8） | ✅ | 見 §4 列舉 | 該列資料品質狀態 |

**Index**：`pandas.DatetimeIndex`，名稱 `date`，dtype `datetime64[ns]`，無時區（UTC
naive；FR-007 明確聲明）；單調遞增、唯一。

**列數預估**：2018-01-01 至 2026-04-29 之 NYSE 交易日約 2,090 列／檔。

---

## 2. Rate Snapshot Parquet Schema

**用途**：FRED 3-month T-bill rate（series ID: DTB3）日線快照。

**檔名**：`dtb3_daily_<startYYYYMMDD>_<endYYYYMMDD>.parquet`
（例：`dtb3_daily_20180101_20260429.parquet`）

| 欄位 | dtype | 必要 | 值域 | 說明 |
|---|---|---|---|---|
| `rate_pct` | `float64` | ✅ | [-∞, ∞] ∪ {NaN} | 年化 T-bill rate（百分比，例 5.25 表 5.25%） |
| `quality_flag` | `string` | ✅ | 見 §4 列舉 | 該列資料品質狀態 |

**Index**：`pandas.DatetimeIndex`，名稱 `date`，dtype `datetime64[ns]`，無時區；
單調遞增、唯一。

**列數預估**：FRED 對 DTB3 提供每銀行日資料，2018-01-01 至 2026-04-29 約 2,170 列。

---

## 3. Snapshot Metadata JSON Schema

**用途**：與每個 Parquet 一對一伴隨的 metadata 檔，承載可重現性所有上下文（FR-012）。
完整 JSON Schema 定義見 `contracts/snapshot-metadata.schema.json`，本節為人類可讀概覽。

**檔名**：`<parquet_filename>.meta.json`
（例：`nvda_daily_20180101_20260429.parquet.meta.json`）

```jsonc
{
  "schema_version": "1.0",                    // 本 metadata schema 版本（後向相容用）
  "fetch_timestamp_utc": "2026-04-29T03:14:15Z",  // ISO 8601 含 Z（FR-014）
  "data_source": "yfinance",                  // 列舉："yfinance" | "fred"
  "data_source_call_params": {                // 原始呼叫參數（資料源 client 介面）
    "ticker": "NVDA",
    "start": "2018-01-01",
    "end": "2026-04-30",                      // 內部轉換後傳給 yfinance（end+1）
    "auto_adjust": true,
    "interval": "1d"
  },
  "upstream_package_versions": {              // 抓取時動態查詢
    "yfinance": "0.2.43",
    "pyarrow": "15.0.2",
    "pandas": "2.2.1"
  },
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  // 64 字元 hex
  "row_count": 2087,
  "column_schema": [                          // 與 Parquet 實際 schema 對齊
    {"name": "open", "dtype": "float64"},
    {"name": "high", "dtype": "float64"},
    {"name": "low", "dtype": "float64"},
    {"name": "close", "dtype": "float64"},
    {"name": "volume", "dtype": "int64"},
    {"name": "quality_flag", "dtype": "string"}
  ],
  "index_schema": {"name": "date", "dtype": "datetime64[ns]", "tz": null},
  "time_range": {                             // 實際資料起訖（不是設定值）
    "start": "2018-01-02",                    // 第一個交易日
    "end": "2026-04-29"
  },
  "quality_summary": {                        // 各 quality_flag 出現列數
    "ok": 2080,
    "missing_close": 0,
    "zero_volume": 5,
    "missing_rate": 0,
    "duplicate_dropped": 2
  },
  "duplicate_dropped_timestamps": [           // 被丟棄的重複日（FR-011）
    "2020-03-23",
    "2022-06-14"
  ]
}
```

**驗證規則**（由 `jsonschema` 套件執行，research R10）：
- `schema_version` MUST 為 `"1.0"`（本 feature 僅支援 v1.0）。
- `fetch_timestamp_utc` MUST 符合 ISO 8601 + `Z` 後綴（pattern：`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$`）。
- `data_source` MUST ∈ `{"yfinance", "fred"}`。
- `sha256` MUST 為 64 字元小寫 hex。
- `row_count` MUST 等於 Parquet 實際列數（驗證指令會比對）。
- `quality_summary` 各值總和 MUST 等於 `row_count`。
- `unevaluatedProperties: false` — 禁止任何 schema 未列舉欄位。

---

## 4. Quality Flag 列舉

**用途**：每列資料的品質狀態標示（spec FR-009、FR-010），以下游 feature 可直接以
字串比對篩選。

| 值 | 適用 | 含義 |
|---|---|---|
| `"ok"` | 全部 | 該列為有效資料，所有必要欄位齊全 |
| `"missing_close"` | OHLCV | `close` 為 NaN（含 `open/high/low/volume` 任一為 NaN） |
| `"zero_volume"` | OHLCV | `volume == 0`（停牌或無交易） |
| `"missing_rate"` | Rate | `rate_pct` 為 NaN（FRED 該日無觀測值） |
| `"duplicate_dropped"` | 全部 | 此列**不**出現於 Parquet（保留首次後丟棄重複，僅出現於 `quality_summary` 統計） |

**判定優先序**（同列同時觸發多條件時取上位）：
1. `missing_close` / `missing_rate`（缺值優先標示）
2. `zero_volume`（僅 OHLCV 適用）
3. `ok`（預設）

`duplicate_dropped` 不會出現於 Parquet 列的 `quality_flag` 欄（被丟棄的列不在輸出中），
僅見於 metadata 的 `quality_summary` 與 `duplicate_dropped_timestamps`。

---

## 5. Ingestion Configuration

**用途**：使用者可修改的設定，驅動抓取與重建（spec Key Entity）。

```python
@dataclass(frozen=True)
class IngestionConfig:
    tickers_risk_on: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU")
    tickers_risk_off: tuple[str, ...] = ("GLD", "TLT")
    fred_series_id: str = "DTB3"
    start_date: str = "2018-01-01"          # ISO 8601 date，inclusive
    end_date: str = "2026-04-29"            # inclusive（FR-005）
    output_dir: Path = Path("data/raw")
    interval: Literal["1d"] = "1d"          # 僅日線（FR-023）
    auto_adjust: bool = True                # FR-006
    snappy_compression: bool = True         # FR-004
    max_retry_attempts: int = 5             # research R3
    retry_base_seconds: float = 1.0
    retry_multiplier: float = 2.0
```

**驗證規則**（建構階段拋 `ValueError`）：
- `start_date` 與 `end_date` MUST 為合法 ISO 8601 date 字串。
- `start_date <= end_date`。
- `tickers_risk_on + tickers_risk_off` MUST 為非空、無重複、全大寫字母。
- `fred_series_id` MUST 非空字串。
- `output_dir` MUST 為相對或絕對路徑（不檢查存在性，由抓取流程建立）。

**配置來源**：
1. 預設值（如上 dataclass）。
2. 環境變數覆寫（`PPO_SMC_INGEST_START_DATE` 等，CI 用）。
3. CLI 參數覆寫（最高優先序）。

---

## 6. Internal Entities

### 6.1 `RawAssetData`（中介結構，不持久化）

```python
@dataclass(frozen=True)
class RawAssetData:
    ticker: str
    df: pd.DataFrame          # yfinance 原始回傳，未經 quality_flag 處理
    fetched_at_utc: datetime  # 抓取完成時間戳
    package_versions: Mapping[str, str]
    call_params: Mapping[str, Any]
```

**生命週期**：抓取成功後即建立，傳遞至 quality processing → Parquet writer →
metadata writer，全程持有於記憶體；不寫至 staging 目錄之外的位置。

### 6.2 `RawRateData`

```python
@dataclass(frozen=True)
class RawRateData:
    series_id: str
    series: pd.Series         # FRED 原始回傳
    fetched_at_utc: datetime
    package_versions: Mapping[str, str]
    call_params: Mapping[str, Any]
```

### 6.3 `SnapshotArtifact`（寫入結果）

```python
@dataclass(frozen=True)
class SnapshotArtifact:
    parquet_path: Path
    metadata_path: Path
    sha256: str
    row_count: int
    quality_summary: Mapping[str, int]
```

`fetch` CLI 的最終回傳 = `tuple[SnapshotArtifact, ...]`（7 個元素）。

---

## 7. 目錄結構

```text
data/
└── raw/
    ├── nvda_daily_20180101_20260429.parquet
    ├── nvda_daily_20180101_20260429.parquet.meta.json
    ├── amd_daily_20180101_20260429.parquet
    ├── amd_daily_20180101_20260429.parquet.meta.json
    ├── tsm_daily_20180101_20260429.parquet
    ├── tsm_daily_20180101_20260429.parquet.meta.json
    ├── mu_daily_20180101_20260429.parquet
    ├── mu_daily_20180101_20260429.parquet.meta.json
    ├── gld_daily_20180101_20260429.parquet
    ├── gld_daily_20180101_20260429.parquet.meta.json
    ├── tlt_daily_20180101_20260429.parquet
    ├── tlt_daily_20180101_20260429.parquet.meta.json
    ├── dtb3_daily_20180101_20260429.parquet
    └── dtb3_daily_20180101_20260429.parquet.meta.json
```

抓取過程中暫存於 `data/raw/.staging-<UTC_timestamp>/` 同樣結構，全部成功後逐檔
`os.replace()` 至 `data/raw/`（research R5）。

---

## 8. 跨 Feature Schema 相容性

與 feature 001（smc-feature-engine）的接口契約：

| 002 輸出 | 001 視為 |
|---|---|
| `open`, `high`, `low`, `close`, `volume`（OHLCV Parquet） | 直接餵入 `batch_compute(df)`（dtype 完全相容） |
| `quality_flag`（OHLCV Parquet） | 001 spec FR-014 識別 `!= "ok"` 列輸出 NaN |
| index（datetime64[ns]） | 001 直接使用為 DataFrame index |
| `rate_pct`（Rate Parquet） | 003 PPO feature 用於 reward / Sharpe；001 不使用 |

**無轉換層**：`pd.read_parquet("data/raw/nvda_daily_*.parquet")` 即可餵入 001 的
`batch_compute`。

---

## 9. 不變式（Invariants）

實作 MUST 維護以下不變式，CI 測試應驗證：

1. **檔名規約嚴格**：所有 Parquet 與 metadata 檔名 MUST 符合 `<ticker>_daily_<start>_<end>.parquet[.meta.json]` 模式（FR-002、FR-003）。
2. **一對一對應**：每個 Parquet MUST 有對應 metadata；每個 metadata MUST 有對應 Parquet。驗證指令偵測缺失。
3. **SHA-256 一致性**：metadata 中 `sha256` MUST 等於對應 Parquet 二進位內容的 hashlib.sha256 hex digest（FR-013）。
4. **列數一致性**：metadata 中 `row_count` MUST 等於 Parquet 實際列數，且等於 `quality_summary` 各值總和。
5. **Schema 一致性**：metadata 中 `column_schema` MUST 等於 Parquet 實際 schema。
6. **時間戳格式**：所有 metadata 的 timestamp 欄位 MUST 為 UTC 且 ISO 8601 + `Z` 後綴（FR-014）。
7. **不修補政策**：任何 quality_flag != "ok" 列的數值欄位 MUST 保留 NaN 或原始零值，不得被插值或前向填補（FR-010）。
8. **原子性**：`data/raw/` 中所有檔案要嘛全部來自單次成功抓取、要嘛全部來自先前成功版本；不存在「部分檔案來自失敗的部分抓取」狀態（FR-018、SC-004）。
9. **Frozen 配置**：`IngestionConfig` 與 metadata 載入後的 dataclass 為 frozen，不允許就地修改。
10. **byte-identical（同一抓取時點）**：同一 commit 下，相同網路條件、相同套件版本、相同設定，兩次抓取產出的 Parquet 檔 MUST byte-identical（SC-007；忽略 metadata 中的 `fetch_timestamp_utc`）。
