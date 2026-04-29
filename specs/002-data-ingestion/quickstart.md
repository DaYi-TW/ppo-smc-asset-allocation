# Quickstart: 002-data-ingestion

**Audience**：新加入的研究者 / 合作者 / CI 維護者。
**Goal**：5 分鐘內從零完成「安裝 → 抓取快照 → 驗證 → 在 Python 載入」全流程。

---

## 0. 前置需求

| 項目 | 版本 | 備註 |
|------|------|------|
> **重要**：本 feature 的官方支援與重現環境為 **Docker container**。直接在 host
> Python 跑屬非官方路徑、不保證憲法 SC-007 byte-identical Parquet 結果。

| 項目 | 版本 | 備註 |
|------|------|------|
| Docker Engine | ≥ 24.0 | Linux：原生；macOS / Windows：Docker Desktop |
| Docker Compose | ≥ 2.20 | 隨 Docker Desktop 一併安裝 |
| 網路 | ≥ 50 Mbps | SC-001 的 5 分鐘基準（image build + fetch） |
| 磁碟 | ≥ 1 GB 自由空間 | image ~400 MB + 暫存 + 最終輸出（最終 < 10 MB，SC-005） |
| FRED API key | 必要 | 免費註冊：https://fred.stlouisfed.org/docs/api/api_key.html |

**取得 FRED API key**（一次性，30 秒）：

1. 前往上方連結，建立帳號（免費）。
2. 在「My Account → API Keys」頁面建立新 key（32 字元 hex）。
3. 寫入 repo 根目錄 `.env` 檔（**不會被 commit**，已列入 `.gitignore`）：

   ```bash
   cp .env.example .env
   # 編輯 .env，填入：
   #   FRED_API_KEY=your_32_char_hex_key_here
   ```

   `docker-compose.yml` 會自動讀取 `.env` 並注入容器環境變數。

**驗證 Docker 可用**：

```bash
docker --version          # 應 >= 24.0
docker compose version    # 應 >= 2.20
```

---

## 1. Build 容器映像（首次，~3 分鐘）

從 repo 根目錄執行：

```bash
docker compose build dev
```

預期輸出末段：

```text
 => => naming to docker.io/library/ppo-smc-asset-allocation-dev:latest
```

驗證容器內 CLI 可用：

```bash
docker compose run --rm dev ppo-smc-data --version
# 預期：ppo-smc-data 0.1.0
```

**Tip — 開 shell 進容器互動**（推薦日常開發用法）：

```bash
docker compose run --rm dev bash
# 容器內 prompt：dev@<container_id>:/workspace$
# 後續所有 ppo-smc-data / pytest 指令直接執行
# 退出：exit
```

以下 §2–§9 的指令範例均假設你在容器 shell 內；若要從 host 一次性呼叫，請前綴
`docker compose run --rm dev`。

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
- name: Build dev image
  run: docker compose build dev

- name: Verify data snapshots
  run: docker compose run --rm dev ppo-smc-data verify
  # 不需 FRED_API_KEY；不需網路；應於 < 5 秒完成（容器啟動 + verify）

- name: Run test suite
  run: docker compose run --rm dev pytest --cov=data_ingestion
```

由於快照本身已 commit 進 repo，CI 僅需 verify、不需重新 fetch。所有步驟在容器內
執行確保 byte-identical 基準一致（憲法 SC-007）。

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

## 9. 跑單元測試（容器內）

```bash
# 容器內 shell：
pytest tests/
# 預期：所有測試通過，覆蓋率 ≥ 90%（與 001 一致）

# 從 host 一次性呼叫：
docker compose run --rm dev pytest tests/
```

特別是：

```bash
pytest tests/contract/test_metadata_schema.py    # 驗證 metadata JSON Schema
pytest tests/integration/test_atomic_fetch.py    # 驗證 staging + rename 原子性
pytest tests/unit/test_quality.py                # 驗證 quality_flag 列舉判定
```

---

## 10. （非官方）直接在 host Python 執行

不裝 Docker 也能跑，但**不在憲法 SC-007 byte-identical 保證範圍內**，僅供快速 debug：

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\Activate.ps1         # Windows PowerShell
pip install -e . -r requirements-lock.txt
ppo-smc-data --version
```

若 host 與容器產出 Parquet SHA-256 不一致，以容器為準（重現實驗請用 Docker）。

---

## 完成

跑通本流程代表：

- ✅ 你已可重現整個資料層（憲法 Principle I）。
- ✅ CI 可獨立執行驗證。
- ✅ 下游 feature 001 / 003 可直接消費快照。

下一步：依 `/speckit.tasks` 產生的任務序進入 `/speckit.implement`，或直接前往
[001-smc-feature-engine quickstart](../001-smc-feature-engine/quickstart.md)
開始計算特徵。
