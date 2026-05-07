# tests/fixtures/

供 SMC Feature Engine 與 Data Ingestion 測試共用的小型資料 fixture。

## 結構

```
fixtures/
├── golden_snapshots/      # 002-data-ingestion 跨平台 byte-identical 證明
│   ├── golden_daily_20240102_20240131.parquet
│   └── golden_daily_20240102_20240131.parquet.meta.json
├── nvda_2024H1.parquet    # 001 small_ohlcv（~125 列，單元測試用）
├── nvda_2023_2024.parquet # 001 sample_ohlcv（~500 列，integration / 性能基準用）
└── README.md              # 本檔案
```

## 來源與重建

`nvda_2024H1.parquet` 與 `nvda_2023_2024.parquet` 由 `data/raw/` 中的
NVDA 完整快照子集抽出，由 `scripts/build_smc_fixtures.py` 在 dev container
內產生（見 specs/001-smc-feature-engine/quickstart.md §4）。

重建方式（**僅當有意更新 fixture 範圍時**）：

```bash
docker compose run --rm dev python scripts/build_smc_fixtures.py
```

重建後若 SHA-256 改變，相關測試的 expected hash 需同步更新。

## 為何 commit 進 repo

- 跨平台測試（spec SC-002，atol = 1e-9）需要固定輸入。
- 大小遠 < 1 MB，不會撐爆 repo（憲法 SC-005 的 10 MB 門檻仍綽綽有餘）。
- 由 `.gitattributes` 標為 binary，避免 Windows checkout 時 EOL 翻譯。
