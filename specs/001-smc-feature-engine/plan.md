# Implementation Plan: 001-smc-feature-engine

**Branch**: `001-smc-feature-engine` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-smc-feature-engine/spec.md`

## Summary

將 Smart Money Concepts（BOS、CHoCh、FVG、OB）從主觀盤勢判讀轉為可量化、可重現、可
視覺化覆核的純函式庫，作為後續 PPO 訓練的觀測空間特徵來源。技術路線：以 pandas /
numpy 向量化批次計算為主，並提供 frozen dataclass 形式的引擎狀態以支援增量模式
（batch / incremental 等價，spec FR-008）；視覺化以 mplfinance（PNG）與 plotly
（HTML）雙管道輸出；跨平台浮點 byte-identical 透過 IEEE 754 float64 + 禁用 SIMD
reduce + 套件版本鎖定（research R5、R7）達成。

## Technical Context

**Language/Version**: Python 3.11+（CI 同時驗 3.11 與 3.12）
**Primary Dependencies**: pandas ≥ 2.0、numpy、pyarrow（Parquet I/O，與 feature 002
產出格式一致）；視覺化使用 mplfinance（PNG）+ plotly（HTML）雙函式庫（research R4）；
測試 pytest + pytest-cov
**Storage**: 不直接寫檔；下游讀取 002 產出的 Parquet 快照，本 feature 為純函式庫
**Testing**: pytest（含 parametrize、fixture），coverage ≥ 90%（spec SC-004）；
視覺化人類可讀性（spec SC-005）採人工受試流程，於 quickstart.md §3 描述
**Target Platform**: Linux / macOS / Windows，跨平台 byte-identical（atol = 1e-9，
spec SC-002，research R5）
**Project Type**: Single project — 純 Python 函式庫 package；原始碼 `src/smc_features/`、
測試 `tests/{contract,integration,unit}/`
**Performance Goals**: 批次 NVDA 兩年日線 < 30 秒（spec SC-001）；增量單根 K 棒
< 10 ms（spec SC-003）
**Constraints**: 純單執行緒 deterministic、不依賴系統時間或亂數、跨平台 byte-identical
浮點輸出；frozen dataclass 禁止就地修改；NaN 列不污染下游視窗（spec FR-015）
**Scale/Scope**: 6 檔資產 × 約 8 年日線（每檔約 2,000 列），預期單檔批次 < 5 秒；
公開 API 僅三個進入點（`batch_compute` / `incremental_compute` / `visualize`）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` v1.1.0 五大原則逐條檢視（v1.1.0 僅變更後端 Java/Spring Boot 版本，本 feature 為純 Python 函式庫不受影響）：

| # | 原則 | 是否適用 | 合規策略 | 狀態 |
|---|---|---|---|---|
| I | 可重現性（NON-NEGOTIABLE）| ✅ 適用 | 無亂數來源（無需固定 seed），但 (a) `pyproject.toml` 鎖定主要相依範圍 + `requirements-lock.txt` 精確鎖版（research R7）；(b) 禁用多執行緒 reduce、固定 numpy 浮點順序（research R5）；(c) 跨平台 CI 以 atol = 1e-9 比對 reference fixture（spec SC-002）。 | ✅ Pass |
| II | 特徵可解釋性 | ✅ 適用 | 每個特徵函式 docstring MUST 含判定規則的數學定義（research R1–R3）；提供 `visualize()` 對應疊加圖；單元測試對每個規則含正反案例（spec FR-005、FR-009、FR-010、FR-011）。 | ✅ Pass |
| III | 風險優先獎勵（NON-NEGOTIABLE）| ❌ 不適用 | 本 feature 為特徵工程函式庫，不含 reward function。後續 PPO 訓練 feature 需在自身 plan 中對此原則合規。 | ✅ N/A documented |
| IV | 微服務解耦 | ✅ 適用（弱）| 本 feature 為純函式庫，僅在 Python AI 引擎進程內被 import。未來後端 Java 服務若要消費，MUST 透過 HTTP API 包裝（屬未來 feature 範圍），不得跨層共享記憶體。 | ✅ Pass |
| V | 規格先行（NON-NEGOTIABLE）| ✅ 適用 | `spec.md` 已通過 review gate；本 plan 為 `/speckit.plan` 合規後續產物；後續 `/speckit.tasks`、`/speckit.implement` 階段順序不可重排。 | ✅ Pass |

**Initial gate（Phase 0 前）**：✅ 全部通過，無違規。
**Post-design gate（Phase 1 後）**：✅ 維持通過 — Phase 1 產出（data-model.md、
contracts/api.pyi、quickstart.md）未引入任何違反原則的設計選擇；frozen dataclass
強化 Principle I，type stubs 強化 Principle II，純函式庫設計天然符合 Principle IV。

## Project Structure

### Documentation (this feature)

```text
specs/001-smc-feature-engine/
├── plan.md              # 本檔案（/speckit.plan 輸出）
├── spec.md              # /speckit.specify 輸出（已通過 review gate）
├── research.md          # Phase 0 輸出（七項技術決策）
├── data-model.md        # Phase 1 輸出（資料結構與不變式）
├── quickstart.md        # Phase 1 輸出（5 分鐘上手流程）
├── contracts/
│   └── api.pyi          # Phase 1 輸出（公開 API type stubs）
└── tasks.md             # Phase 2 輸出（/speckit.tasks 產生，本指令不產）
```

### Source Code (repository root)

採 **Single project** layout（純 Python 函式庫）：

```text
src/
└── smc_features/
    ├── __init__.py            # 公開 API re-export（與 contracts/api.pyi 對齊）
    ├── types.py               # SMCFeatureParams、SwingPoint、FVG、OrderBlock、SMCEngineState、FeatureRow、BatchResult
    ├── swing.py               # Swing high/low 偵測（research R1）
    ├── structure.py           # BOS / CHoCh 判定（research R1）
    ├── fvg.py                 # FVG 偵測與填補追蹤（research R2）
    ├── ob.py                  # Order Block 偵測、ATR、距離標準化（research R3）
    ├── batch.py               # batch_compute() 主入口
    ├── incremental.py         # incremental_compute() 主入口 + state 推進
    └── viz/
        ├── __init__.py
        ├── mpl_backend.py     # mplfinance PNG renderer
        └── plotly_backend.py  # plotly HTML renderer

tests/
├── contract/                  # 對 contracts/api.pyi 的簽章與不變式測試（data-model.md §9）
│   ├── test_public_api.py
│   └── test_invariants.py
├── integration/               # 跨模組與 batch/incremental 等價性
│   ├── test_batch_incremental_equivalence.py
│   ├── test_quality_flag_propagation.py
│   └── test_cross_platform_fixture.py
└── unit/                      # 單一規則正反案例
    ├── test_swing.py
    ├── test_bos.py
    ├── test_choch.py
    ├── test_fvg.py
    ├── test_ob.py
    └── test_atr.py

pyproject.toml                  # 套件中繼資料與相依範圍
requirements-lock.txt           # 完全鎖版本（research R7）
```

**Structure Decision**: 採 Single project 函式庫 layout。理由：
1. 本 feature 為純運算函式庫，無 server / client / mobile 三層分離需求。
2. `src/` layout（PEP 621 推薦）讓開發階段必須 `pip install -e .` 才能 import，
   避免測試誤抓專案根目錄的同名模組，強化可重現性（Principle I）。
3. 視覺化雙後端拆 `viz/` 子套件，使核心計算與繪圖相依解耦 — 後續若要 headless 部署
   可只裝核心，不需 mplfinance / plotly。
4. `tests/{contract,integration,unit}/` 三層分流對應憲法 Principle II（特徵可解釋性需
   單元正反案例）與 SC-004（coverage ≥ 90%）。

## Complexity Tracking

> 無違規，本節留空。Constitution Check 全部 Pass 或 N/A documented。
