# Implementation Plan: 002-data-ingestion

**Branch**: `002-data-ingestion` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-data-ingestion/spec.md`

## Summary

建立可重現的歷史資料快照層：以單一 CLI 指令從 Yahoo Finance 抓取六檔股票/ETF
（NVDA、AMD、TSM、MU、GLD、TLT）日線 OHLCV、從 FRED 抓取 DTB3 利率序列，產出
帶 quality_flag 的 Parquet 檔（snappy 壓縮）與 SHA-256 metadata sidecar，commit
進 `data/raw/`。技術路線：yfinance + fredapi（research R1、R2）負責抓取；tenacity
（R3）負責有限重試；pyarrow 配合鎖定參數實現跨平台 byte-identical Parquet（R4）；
staging 目錄 + atomic rename（R5）保證原子性；獨立 verify CLI 透過 jsonschema +
hashlib（R6、R10）執行純本地驗證；argparse（R8）暴露三個子指令 `fetch / verify /
rebuild`。直接服務於下游 001-smc-feature-engine 與後續 PPO 訓練 feature。

## Technical Context

**Language/Version**: Python 3.11+（CI 同時驗 3.11 與 3.12，與 001 一致）
**Primary Dependencies**: yfinance ~= 0.2.40、fredapi ~= 0.5.2、pyarrow ~= 15.0、
pandas >= 2.0、tenacity ~= 8.2、jsonschema ≥ 4.20；CLI 使用標準函式庫 argparse；
測試 pytest + pytest-cov（與 001 共用）
**Dev / Run Environment**: **Docker（Linux container）為唯一官方支援的開發與重現環境**。
基底映像 `python:3.11-slim`；repo 根目錄含 `Dockerfile`、`docker-compose.yml`、
`.dockerignore`。所有指令（`ppo-smc-data fetch / verify / rebuild`、`pytest`）皆於
容器內執行；source code 與 `data/raw/` 由 host bind mount 進入容器以利編輯與 commit。
直接在 host Python 執行屬非官方路徑，不保證 byte-identical（憲法 SC-007 基準鎖定為
Linux container 環境）。
**Storage**: 本地檔案系統 `data/raw/*.parquet` + `*.parquet.meta.json`，
透過 git commit 進行版本控管（憲法 Principle I 載體）
**Testing**: pytest（含 parametrize、fixture、`pytest.mock` 覆蓋網路 client），
coverage ≥ 90%（沿用 001 標準）；網路測試以 vcrpy 或預錄 fixture 隔離；
所有測試於 container 內執行（`docker compose run --rm dev pytest`）
**Target Platform**: 重現基準為 Linux container（python:3.11-slim）；host OS 為
Linux / macOS / Windows + Docker Desktop。憲法 SC-007 byte-identical 要求由統一容器
環境保證（research R4 的 pyarrow writer 參數鎖定仍生效，但跨 host OS 差異被容器
隔離吸收）。
**Project Type**: Single project — 純 Python CLI + 函式庫 package；原始碼
`src/data_ingestion/`、測試 `tests/{contract,integration,unit}/`，與 001 並列於
同一 monorepo 但 package 名稱獨立
**Performance Goals**: SC-001 全程 fetch < 5 分鐘（≥ 50 Mbps 網路）；SC-003 載入
單一 Parquet < 100 ms（SSD）；SC-005 全部 7 檔總大小 < 10 MB
**Constraints**: SC-007 同 commit 同條件下 byte-identical；SC-004 原子性（all-or-
nothing 寫入）；無亂數、無 jitter（research R3）；無互動模式預設（CI 友善）
**Scale/Scope**: 7 個快照檔案、~14k 列總資料、單次 fetch ~30 個 HTTP 請求（含重試
餘裕）；三個 CLI 子指令、~10 個公開 Python API symbol（contracts/api.pyi）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` v1.1.0 五大原則逐條檢視：

| # | 原則 | 是否適用 | 合規策略 | 狀態 |
|---|---|---|---|---|
| I | 可重現性（NON-NEGOTIABLE）| ✅ **核心適用** | (a) 快照 commit 進 repo（spec FR-002）；(b) metadata 紀錄套件版本、call params、SHA-256（FR-012、research R7）；(c) Parquet writer 參數鎖定使跨平台 byte-identical（research R4）；(d) 獨立 verify CLI 純本地檢查（FR-015、SC-002）；(e) 重試策略無 jitter、無亂數（research R3）；(f) 原子性寫入避免半完成狀態（FR-018、research R5）。 | ✅ Pass |
| II | 特徵可解釋性 | ❌ 不適用 | 本 feature 為原始資料層，不計算任何衍生特徵（spec FR-022 顯式排除）；解釋性要求由下游 001 承擔。 | ✅ N/A documented |
| III | 風險優先獎勵（NON-NEGOTIABLE）| ❌ 不適用 | 本 feature 不含 reward function；後續 PPO 訓練 feature 將消費本 feature 輸出的 DTB3 作為無風險利率，但 reward 設計屬該 feature 範圍。 | ✅ N/A documented |
| IV | 微服務解耦 | ✅ 適用（弱）| 本 feature 為純 CLI + 函式庫，於 Python AI 引擎進程內被 import；未產生跨層共享狀態。未來若後端 Java 服務需消費快照，MUST 透過 HTTP API 或 Kafka 訊息（屬未來 feature 範圍）。 | ✅ Pass |
| V | 規格先行（NON-NEGOTIABLE）| ✅ 適用 | `spec.md` 已通過 review gate；本 plan 為 `/speckit.plan` 合規後續產物；後續 `/speckit.tasks`、`/speckit.implement` 階段順序不可重排。 | ✅ Pass |

**Initial gate（Phase 0 前）**：✅ 全部通過，無違規。
**Post-design gate（Phase 1 後）**：✅ 維持通過 — Phase 1 產出（data-model.md、
contracts/cli.md、contracts/snapshot-metadata.schema.json、contracts/api.pyi、
quickstart.md）強化 Principle I（JSON Schema 阻擋 metadata 誤改、frozen dataclass
保證配置不可變、atomic rename 設計細化原子性）；無新引入違規。

## Project Structure

### Documentation (this feature)

```text
specs/002-data-ingestion/
├── plan.md                              # 本檔案（/speckit.plan 輸出）
├── spec.md                              # /speckit.specify 輸出（已通過 review gate）
├── research.md                          # Phase 0 輸出（10 項技術決策 R1–R10）
├── data-model.md                        # Phase 1 輸出（schema、不變式、配置）
├── quickstart.md                        # Phase 1 輸出（5 分鐘上手流程）
├── contracts/
│   ├── cli.md                           # Phase 1 輸出（CLI 退出代碼、stdout 格式契約）
│   ├── snapshot-metadata.schema.json    # Phase 1 輸出（metadata JSON Schema）
│   └── api.pyi                          # Phase 1 輸出（公開 Python API type stubs）
├── checklists/
│   └── requirements.md                  # /speckit.specify 階段產出
└── tasks.md                             # Phase 2 輸出（/speckit.tasks 產生，本指令不產）
```

### Source Code (repository root)

採 **Single project** layout（純 Python CLI + 函式庫，與 001 並列於同 monorepo）：

```text
src/
├── smc_features/                        # 已由 001 plan 規劃，不在本 feature 範圍
└── data_ingestion/
    ├── __init__.py                      # 公開 API re-export（與 contracts/api.pyi 對齊）
    ├── config.py                        # IngestionConfig dataclass + 驗證
    ├── quality.py                       # quality_flag 判定（data-model.md §4）
    ├── sources/
    │   ├── __init__.py
    │   ├── yfinance_source.py           # yfinance 抓取 + 重試（research R1、R3）
    │   └── fred_source.py               # fredapi 抓取 + 重試（research R2、R3）
    ├── writer.py                        # Parquet 寫入（research R4 byte-identical 設定）
    ├── metadata.py                      # metadata JSON 產出 + JSON Schema 驗證（research R10）
    ├── hashing.py                       # SHA-256 chunked 計算（research R6）
    ├── atomic.py                        # staging dir + os.replace 原子性（research R5）
    ├── verify.py                        # 驗證流程（公開 API：verify_snapshot / verify_all）
    ├── loader.py                        # 公開 API：load_asset_snapshot / load_rate_snapshot / load_metadata
    └── cli.py                           # argparse 進入點（fetch / verify / rebuild）

data/
└── raw/                                 # 抓取輸出（commit 進 repo，憲法 Principle I 載體）
    ├── *.parquet
    └── *.parquet.meta.json

tests/
├── contract/                            # 對 contracts/ 的簽章與不變式測試
│   ├── test_public_api.py
│   ├── test_cli_exit_codes.py
│   └── test_metadata_schema.py
├── integration/                         # 跨模組與端對端流程
│   ├── test_atomic_fetch.py
│   ├── test_verify_roundtrip.py
│   ├── test_cross_platform_fixture.py
│   └── test_load_perf.py                # SC-003 < 100 ms
└── unit/                                # 單元正反案例
    ├── test_config.py
    ├── test_quality.py
    ├── test_writer_determinism.py        # R4 跨次寫入 byte-identical
    ├── test_hashing.py
    ├── test_metadata.py
    └── test_loader.py

pyproject.toml                            # 套件中繼資料；新增 [project.scripts] ppo-smc-data
requirements-lock.txt                     # 完全鎖版本（與 001 共用，新增本 feature 相依）
Dockerfile                                # python:3.11-slim 基底，安裝 pyproject + lock；
                                          # non-root user (uid=1000) 寫入 data/raw/ 不會
                                          # 留 root-owned 檔案
docker-compose.yml                        # 服務 `dev`：bind mount repo root → /workspace；
                                          # 注入 FRED_API_KEY；entrypoint 為 bash
.dockerignore                             # 排除 .git / .venv / .pytest_cache / data/raw/
                                          # （後者由 mount 進入而非 build context）
```

**Structure Decision**: 採 Single project monorepo。理由：
1. 002 與 001 共用 `pyproject.toml` 與 `requirements-lock.txt`，避免兩個 package
   各自鎖版導致下游必須安裝兩次；Principle I 也偏好單一鎖檔 source-of-truth。
2. `src/data_ingestion/` 與 `src/smc_features/` 同層獨立，各自有 `__init__.py`
   re-export 公開 API；除型別 dataclass 外無跨 package import（保持 IV 弱解耦）。
3. `data/raw/` 與 `src/` 並列於 repo 根目錄；資料不放 `src/` 內以免被誤打包進
   wheel；commit 進 git 為 Principle I 的物理載體。
4. 單一 `tests/` 目錄按 contract / integration / unit 三層分流；命名前綴
   （`test_writer_*`、`test_load_*`）區分 002 與 001 測試。
5. CLI 進入點 `ppo-smc-data` 透過 `pyproject.toml` 的 `[project.scripts]` 註冊；
   亦可 `python -m data_ingestion.cli` 呼叫（CI 友善）。
6. Docker 檔案（`Dockerfile`、`docker-compose.yml`、`.dockerignore`）置於 repo 根目錄
   而非 `specs/002-data-ingestion/` 內，因其為跨 feature 共用基礎設施（後續 005 推論
   服務、004 訓練迴圈將 reuse 同一 Python image，僅疊加各自相依）。

## Complexity Tracking

> 無違規，本節留空。Constitution Check 全部 Pass 或 N/A documented。
