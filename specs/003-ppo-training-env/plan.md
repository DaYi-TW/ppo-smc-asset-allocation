# Implementation Plan: 003-ppo-training-env

**Branch**: `003-ppo-training-env` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-ppo-training-env/spec.md`

## Summary

建立 Gymnasium 相容的多資產投資組合訓練環境（`PortfolioEnv`），作為 PPO 代理
的互動介面。環境消費 002 的 Parquet 快照與 001 的 SMC 特徵函式庫，於初始化階段
一次性預計算所有特徵與資料 hash 比對（`info["data_hashes"]` 對齊 002 metadata），
step 內僅做查表 + 算術，確保 SC-001 < 30 秒 budget 寬裕。Reward 採風控優先型
`r_t = log(NAV_t / NAV_{t-1}) − λ_mdd × drawdown_t − λ_turnover × turnover_t`，
預設 `λ_mdd=1.0, λ_turnover=0.0015`。Action 為 7 維 simplex，經 NaN 檢查、L1
normalize、0.4 上限封頂三道處理；observation 為 63 維（含 SMC）或 33 維（純價格
ablation），離散與布林 SMC 特徵以 float32 數值編碼（FR-010a）。可重現性由四層
seed 同步（research R1）+ deterministic 算術順序（R2）+ Parquet hash 比對（R6）
保證；跨平台 byte-identical 容差 ≤ 1e-9。本 feature 為純 Python 函式庫，不含
HTTP server / Kafka producer，後者屬 005-008 feature 範圍。

## Technical Context

**Language/Version**: Python 3.11+（CI 同時驗 3.11 與 3.12，與 001/002 一致）
**Primary Dependencies**: gymnasium ~= 0.29、numpy ~= 1.26、pandas >= 2.0；
資料讀取沿用 002 的 `data_ingestion.loader`（pyarrow 透傳）；SMC 特徵由 001
的 `smc_features.batch_compute` 提供；測試 pytest + pytest-cov；不直接依賴
stable-baselines3（屬 004 PPO 訓練 feature 範圍）
**Storage**: 不直接寫檔；輸入為 002 產出的 `data/raw/*.parquet` + metadata
sidecar；環境執行期間僅 in-memory 狀態（NAV history、weights、PRNG）
**Testing**: pytest（含 parametrize、fixture、`pytest.mock` 隔離 002/001
依賴），coverage ≥ 90%（憲法 Spec SC-006）；`gymnasium.utils.env_checker.check_env`
作為 contract test 一環（SC-003）
**Target Platform**: Linux / macOS / Windows，跨平台 byte-identical episode
trajectory 容差 ≤ 1e-9（FR-020、SC-002）；CI 矩陣三平台 × 兩 Python 版本
**Project Type**: Single project — 純 Python 函式庫 package；原始碼
`src/portfolio_env/`、測試 `tests/{contract,integration,unit}/`，與 001、002
並列於同一 monorepo
**Performance Goals**: SC-001 全 episode（~2090 個交易日、Dirichlet 隨機策略）
< 30 秒（單機 CPU）；SMC 特徵於 `__init__` 一次預計算後快取為 numpy 陣列，
step 內 O(1) 查表
**Constraints**: 跨平台 byte-identical 容差 ≤ 1e-9（FR-020）；reset(seed) 同步
四層 seed（numpy / Python random / Gymnasium internal / 環境內部抽樣）（FR-019）；
資料 hash 比對失敗 MUST 於 `__init__` 立即 raise（research R6）；不得依賴全域
`np.random.seed`；環境內部運算順序 deterministic（research R2）
**Scale/Scope**: 6 檔股票 × ~2090 個交易日 ≈ 12.5k 列價格資料；觀測空間 63 維
× 2090 step ≈ 130k 個 float32（~520 KB），SMC 特徵預計算後總 in-memory 狀態
< 5 MB；公開 API 約 5 個 symbol（contracts/api.pyi）：`PortfolioEnv`、
`PortfolioEnvConfig`、`RewardConfig`、`info_to_json_safe`、`make_default_env`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` v1.1.0 五大原則逐條檢視：

| # | 原則 | 是否適用 | 合規策略 | 狀態 |
|---|---|---|---|---|
| I | 可重現性（NON-NEGOTIABLE）| ✅ **核心適用** | (a) `reset(seed=N)` 同步 numpy / Python random / Gymnasium internal / 環境內部抽樣四層 seed（FR-019、research R1）；(b) 不依賴全域 `np.random.seed`；(c) 算術順序固定為「log return → drawdown → turnover → reward」（research R2）；(d) `__init__` 比對 002 metadata SHA-256 雜湊（FR-021、research R6）；(e) 套件版本鎖定於 `pyproject.toml`（pin gymnasium、numpy、pandas）；(f) 不引入任何 jitter / 系統時間相關隨機。CI 矩陣三平台驗證 episode trajectory byte-identical（SC-002）。 | ✅ Pass |
| II | 特徵可解釋性 | ✅ **核心適用** | 本 feature 自身不發明新特徵；所消費的 SMC 特徵已由 001 spec 規範解釋性義務（docstring 數學定義、視覺化、單元測試）。Observation 結構（FR-010）逐維命名公開於 `data-model.md`，每維可追溯回原始物理量；FR-010a 規定布林/離散值的 float32 編碼，避免「神經網路自學中介表示」黑箱。 | ✅ Pass |
| III | 風險優先獎勵（NON-NEGOTIABLE）| ✅ **核心適用** | Reward 三項分量強制存在（FR-006、FR-009）：log_return（階段性報酬）、drawdown_penalty（MDD 懲罰）、turnover_penalty（交易成本懲罰，已涵蓋滑價）。三項於 `info["reward_components"]` 暴露供下游分析；US2 acceptance 與 SC-004/SC-007 提供消融可驗證性。預設權重 `λ_mdd=1.0, λ_turnover=0.0015`（research R3 數值取捨）落實「風控優先」字面意義。 | ✅ Pass |
| IV | 微服務解耦 | ✅ 適用（弱）| 本 feature 為純 Python 函式庫（FR-025），於 AI 引擎進程內被 import；不含 HTTP server / Kafka producer / 資料庫連線。`info` dict 設計為 JSON-serializable（FR-026 + `info_to_json_safe`），便於未來 005 推理服務、007 戰情室透過 HTTP/Kafka 消費 episode log；本 feature 不負責這些 transport 層。 | ✅ Pass |
| V | 規格先行（NON-NEGOTIABLE）| ✅ 適用 | `spec.md` 已通過 review gate（含 4 個 blocking issues 修補 commit `a6a19df`）；本 plan 為 `/speckit.plan` 合規後續產物；後續 `/speckit.tasks`、`/speckit.implement` 階段順序不可重排。 | ✅ Pass |

**Initial gate（Phase 0 前）**：✅ 全部通過，無違規。
**Post-design gate（Phase 1 後）**：✅ 維持通過 — Phase 1 產出（data-model.md、
contracts/api.pyi、contracts/info-schema.json、quickstart.md）強化 Principle I
（observation 維度配置 frozen、info JSON Schema 阻擋誤改、reset 流程細化四層 seed
傳遞順序）與 Principle III（reward_components 三鍵 schema-enforced）；無新引入違規。

## Project Structure

### Documentation (this feature)

```text
specs/003-ppo-training-env/
├── plan.md                              # 本檔案（/speckit.plan 輸出）
├── spec.md                              # /speckit.specify 輸出（已通過 review gate）
├── research.md                          # Phase 0 輸出（8 項技術決策 R1–R8）
├── data-model.md                        # Phase 1 輸出（schema、observation layout、配置）
├── quickstart.md                        # Phase 1 輸出（5 分鐘上手 + 隨機策略 demo）
├── contracts/
│   ├── api.pyi                          # Phase 1 輸出（公開 Python API type stubs）
│   └── info-schema.json                 # Phase 1 輸出（info dict JSON Schema）
├── checklists/
│   └── requirements.md                  # /speckit.specify 階段產出
└── tasks.md                             # Phase 2 輸出（/speckit.tasks 產生，本指令不產）
```

### Source Code (repository root)

採 **Single project** layout（純 Python 函式庫，與 001、002 並列於同 monorepo）：

```text
src/
├── smc_features/                        # 已由 001 plan 規劃，本 feature 消費其 batch_compute
├── data_ingestion/                      # 已由 002 plan 規劃，本 feature 消費其 loader
└── portfolio_env/
    ├── __init__.py                      # 公開 API re-export（與 contracts/api.pyi 對齊）
    ├── config.py                        # PortfolioEnvConfig + RewardConfig dataclass（frozen）
    ├── env.py                           # PortfolioEnv（gymnasium.Env 子類）
    ├── data_loader.py                   # 整合 002 loader + 001 batch_compute + hash 比對
    ├── observation.py                   # observation 組裝（價格特徵 + SMC + macro + weights）
    ├── action.py                        # action 處理（NaN 檢查、L1 normalize、position cap）
    ├── reward.py                        # reward 三項分量計算
    ├── seeding.py                       # 四層 seed 同步（research R1）
    ├── info.py                          # info dict 組裝 + info_to_json_safe
    └── render.py                        # render(mode="ansi") 文字摘要

tests/
├── contract/                            # 對 contracts/ 的簽章與不變式測試
│   ├── test_public_api.py
│   ├── test_gym_check_env.py            # SC-003 env_checker 兩種 config
│   └── test_info_schema.py              # info dict JSON Schema 驗證
├── integration/                         # 跨模組與端對端流程
│   ├── test_random_episode.py           # US1：跑滿一個 episode，no NaN/inf
│   ├── test_reward_components.py        # US2：三項分量加總 == reward
│   ├── test_smc_ablation.py             # US3：63 vs. 33 維對應位置一致
│   ├── test_info_completeness.py        # US4：每步 info key set
│   ├── test_cross_platform_trajectory.py # FR-020 byte-identical（CI 矩陣）
│   ├── test_episode_perf.py             # SC-001 < 30 秒
│   └── test_data_hash_mismatch.py       # FR-021 raise 行為
└── unit/                                # 單元正反案例
    ├── test_config.py                   # frozen dataclass 不可變
    ├── test_action_processing.py        # NaN raise / L1 normalize / position cap
    ├── test_reward_math.py              # log return、drawdown、turnover 算式
    ├── test_observation_layout.py       # 63/33 維分區結構
    ├── test_seeding.py                  # reset(seed) 兩次 trajectory 一致
    ├── test_render_ansi.py              # render(mode="ansi") 格式
    └── test_info_to_json_safe.py        # numpy → list 轉換無精度損失

pyproject.toml                           # 依賴 pin（gymnasium、numpy、pandas、pyarrow 透過 002）
```

**Structure Decision**: Single project（純 Python 函式庫）。`src/portfolio_env/`
與 `src/smc_features/`、`src/data_ingestion/` 並列；其中 `data_loader.py` 是
唯一允許跨 package import 的入口（呼叫 `data_ingestion.loader.load_asset_snapshot`
與 `smc_features.batch_compute`），其他模組保持本 package 內聚。測試三層分流
（contract / integration / unit）與 001、002 一致，便於 CI 共享 fixture
（特別是 002 的 Parquet test fixture）。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違規 — Constitution Check 五項全綠，本表保留結構性占位但無條目。
