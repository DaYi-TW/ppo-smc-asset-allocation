# Quickstart: 002-data-ingestion

**Audience**：新加入的研究者 / 合作者 / CI 維護者。
**Goal**：5 分鐘內從零完成「安裝 → 抓取快照 → 驗證 → 在 Python 載入」全流程。

---

## 0. 前置需求

| 項目 | 版本 | 備註 |
|------|------|------|
| Python | ≥ 3.11 | 與 001 相同；CI 同時驗 3.11 與 3.12 |
| 網路 | ≥ 50 Mbps | SC-001 的 5 分鐘基準 |
| 磁碟 | ≥ 50 MB 自由空間 | 暫存 + 最終輸出（最終 < 10 MB，SC-005） |
| FRED API key | 必要 | 免費註冊：https://fred.stlouisfed.org/docs/api/api_key.html |

**取得 FRED API key**（一次性，30 秒）：

1. 前往上方連結，建立帳號（免費）。
2. 在「My Account → API Keys」頁面建立新 key（32 字元 hex）。
3. 設為環境變數：

   ```bash
   # macOS / Linux
   export FRED_API_KEY="your_32_char_hex_key_here"

   # Windows PowerShell
   $env:FRED_API_KEY = "your_32_char_hex_key_here"

   # Windows CMD
   set FRED_API_KEY=your_32_char_hex_key_here
   ```

4. （建議）寫入 `~/.bashrc` / `~/.zshrc` / PowerShell `$PROFILE` 永久生效。

---

## 1. 安裝（首次）

從 repo 根目錄執行：

```bash
# 建議使用虛擬環境
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\Activate.ps1         # Windows PowerShell

# 安裝（editable + lock file，與 001 共用）
pip install -e .
pip install -r requirements-lock.txt
```

驗證安裝成功：

```bash
ppo-smc-data --version
# 預期：ppo-smc-data 0.1.0
```

---

## 2. 抓取所有快照（一次性，~3 分鐘）

```bash
ppo-smc-data fetch
```

預期輸出：

```text
[fetch] Starting ingestion: 2018-01-01 → 2026-04-29
[fetch] yfinance: NVDA ... ok (2087 rows, sha256=e3b0c44...)
[fetch] yfinance: AMD  ... ok (2087 rows, sha256=12ab34c...)
[fetch] yfinance: TSM  ... ok (2087 rows, sha256=8f4d2e1...)
[fetch] yfinance: MU   ... ok (2087 rows, sha256=a91bcd3...)
[fetch] yfinance: GLD  ... ok (2087 rows, sha256=5c6e7f8...)
[fetch] yfinance: TLT  ... ok (2087 rows, sha256=2b3a4d5...)
[fetch] fred: DTB3     ... ok (2168 rows, sha256=89ef01a...)
[fetch] All 7 snapshots written to data/raw/ in 47.3s
```

執行後檢查：

```bash
ls data/raw/
# 預期：14 個檔案（7 Parquet + 7 .meta.json）
```

---

## 3. 驗證快照（隨時可執行，不需網路）

```bash
ppo-smc-data verify
```

預期輸出（全綠）：

```text
[verify] Scanning data/raw/ ...
[verify] amd_daily_20180101_20260429.parquet  OK  (sha256=12ab34c...)
[verify] dtb3_daily_20180101_20260429.parquet OK  (sha256=89ef01a...)
[verify] gld_daily_20180101_20260429.parquet  OK  (sha256=5c6e7f8...)
[verify] mu_daily_20180101_20260429.parquet   OK  (sha256=a91bcd3...)
[verify] nvda_daily_20180101_20260429.parquet OK  (sha256=e3b0c44...)
[verify] tlt_daily_20180101_20260429.parquet  OK  (sha256=2b3a4d5...)
[verify] tsm_daily_20180101_20260429.parquet  OK  (sha256=8f4d2e1...)
[verify] All 7 snapshots verified successfully.
Exit code: 0
```

**故意製造錯誤試試**（驗證機制有效）：

```bash
# 在任一 Parquet 末尾追加一 byte
echo "x" >> data/raw/nvda_daily_20180101_20260429.parquet
ppo-smc-data verify

# 預期輸出：
# [verify] nvda_daily_20180101_20260429.parquet  FAIL
#          Expected sha256: e3b0c44...
#          Actual sha256:   d72f819...
# Exit code: 1
```

復原：再次執行 `ppo-smc-data fetch` 即覆寫為正確版本。

---

## 4. 在 Python 載入快照（< 100 ms）

```python
import time
from pathlib import Path

from data_ingestion import load_asset_snapshot, load_rate_snapshot, load_metadata

# OHLCV
t0 = time.perf_counter()
nvda = load_asset_snapshot("NVDA")
print(f"NVDA loaded in {(time.perf_counter() - t0) * 1000:.1f} ms")
print(nvda.head())
print(nvda.dtypes)

# 預期 dtypes：
# open            float64
# high            float64
# low             float64
# close           float64
# volume            int64
# quality_flag     string

# 利率
dtb3 = load_rate_snapshot()
print(dtb3.head())

# Metadata
meta = load_metadata(Path("data/raw/nvda_daily_20180101_20260429.parquet"))
print(f"Fetched at: {meta.fetch_timestamp_utc}")
print(f"yfinance version: {meta.upstream_package_versions['yfinance']}")
print(f"Quality summary: {meta.quality_summary}")
```

---

## 5. 重建快照（擴展時間範圍）

例：把起始日改為 2015-01-01。

```bash
ppo-smc-data rebuild --start 2015-01-01 --yes
```

執行後 `data/raw/` 中的檔案被覆寫（檔名因日期變更而改名），舊檔已刪除。立即驗證：

```bash
ppo-smc-data verify
```

---

## 6. CI / 自動化整合

將下列步驟加入 `.github/workflows/ci.yml`（範例）：

```yaml
- name: Verify data snapshots
  run: ppo-smc-data verify
  # 不需 FRED_API_KEY；不需網路；應於 < 5 秒完成
```

由於快照本身已 commit 進 repo，CI 僅需 verify、不需重新 fetch。

---

## 7. 與 001 (smc-feature-engine) 串接

001 的 `batch_compute` 直接吃 002 的輸出，無需轉換：

```python
from data_ingestion import load_asset_snapshot
from smc_features import batch_compute, SMCFeatureParams

nvda = load_asset_snapshot("NVDA")
result = batch_compute(nvda, SMCFeatureParams())
print(result.output.tail())
```

---

## 8. 常見問題排查

| 症狀 | 原因 | 解法 |
|------|------|------|
| `[fetch] ERROR: FRED_API_KEY environment variable is not set.` | 未設定 API key | 回到 §0 設定步驟 |
| `[fetch] ERROR: Failed to download yfinance ticker 'TSM' after 5 retries.` | Yahoo Finance 暫時不可用 | 等待 5–15 分鐘後重試；或檢查網路 |
| `[fetch] ERROR: Disk space insufficient at data/raw/.staging-...` | 磁碟滿 | 清理空間後重試；staging 已自動清除 |
| `[verify] ... FAIL ... Expected vs Actual` | 快照被竄改 | `ppo-smc-data fetch` 重新抓取覆蓋 |
| Windows: `PermissionError: [WinError 5] ...` | 檔案被其他程式佔用 | 關閉 Excel / Power BI 等開啟 Parquet 的程式 |
| 載入耗時 > 1 秒 | 非 SSD 硬碟 / 系統忙碌 | SC-003 預期 SSD；HDD 上時間放寬至 < 500 ms 屬正常 |

---

## 9. 跑單元測試（可選）

```bash
pytest tests/
# 預期：所有測試通過，覆蓋率 ≥ 90%（與 001 一致）
```

特別是：

```bash
pytest tests/contract/test_metadata_schema.py    # 驗證 metadata JSON Schema
pytest tests/integration/test_atomic_fetch.py    # 驗證 staging + rename 原子性
pytest tests/unit/test_quality.py                # 驗證 quality_flag 列舉判定
```

---

## 完成

跑通本流程代表：

- ✅ 你已可重現整個資料層（憲法 Principle I）。
- ✅ CI 可獨立執行驗證。
- ✅ 下游 feature 001 / 003 可直接消費快照。

下一步：依 `/speckit.tasks` 產生的任務序進入 `/speckit.implement`，或直接前往
[001-smc-feature-engine quickstart](../001-smc-feature-engine/quickstart.md)
開始計算特徵。
