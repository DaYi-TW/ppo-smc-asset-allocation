# Implementation Plan: PPO 訓練主迴圈（PPO Training Loop）

**Branch**: `004-ppo-training-loop` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-ppo-training-loop/spec.md`

## Summary

建立 PPO 訓練主迴圈：消費 003 PortfolioEnv 與 stable-baselines3 PPO 演算法，提供單一 CLI entrypoint 從 yaml config 驅動完整訓練流程，支援多 seed 序列執行、SMC ablation 對比、checkpoint 續訓。輸出 run 目錄含 `final_policy.zip`、`metrics.csv`、`metadata.json`、TensorBoard log。本 feature 為純 Python 函式庫（無 HTTP/Kafka/DB），其產出的 `final_policy.zip` 為 005 推理服務的輸入。

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: stable-baselines3 ~= 2.3、gymnasium ~= 0.29（透過 003 包裝）、torch ≥ 2.1（CPU build；GPU 為選項）、numpy、pandas、pyarrow、tensorboard、PyYAML、scipy（Welch's t-test、Cohen's d）、matplotlib（aggregate.png）。測試 pytest + pytest-cov。
**Storage**: 本 feature 無持久化資料庫；artefact 寫入本機檔案系統（`runs/<timestamp>_<git_hash>_seed<N>/`）。讀取 002 的 Parquet 快照（透過 003 env）。
**Testing**: pytest（含 parametrize、tmp_path fixture）、stable-baselines3 內建之 evaluate_policy 用於整合測試。覆蓋率 ≥ 85%（憲法 SC-006）。
**Target Platform**: Linux / macOS / Windows（單機）；典型 CPU 訓練；可選 NVIDIA CUDA GPU 加速。
**Project Type**: Single project（純 Python 套件 `src/ppo_training/` + CLI 入口 `python -m ppo_training.cli`）。
**Performance Goals**: 100k step CPU < 30 min、GPU < 10 min（SC-001）；多 seed (5×100k step) < 2.5 hr CPU。
**Constraints**: 同 commit/seed/config 下 `metrics.csv` byte-identical（SC-003，容差 0.0；浮點寫出採固定 18 位有效數字）；checkpoint 續訓 action 差異 ≤ 1e-6（SC-005，因 PPO advantage normalization 涉及 batch 統計）；資料 hash 比對失敗 MUST raise（FR-019）；NaN/Inf loss 偵測 false negative = 0（SC-007）。
**Scale/Scope**: 單次訓練典型 100k–1M step；多 seed 典型 3–10；不做 hyperparam search、不做多 GPU 分散式。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依憲法 v1.1.0 五大原則展開：

- [x] **I. 可重現性 (NON-NEGOTIABLE)**：FR-009 / SC-003 強制相同 commit + seed + config 下 metrics.csv byte-identical（容差 0.0）。FR-017 同步 4 層 PRNG（Python random、numpy、torch CPU/CUDA、Gymnasium env）。FR-018 套件版本指紋 + FR-019 Parquet hash gate 確保資料污染早期攔截。**Phase 0 research 必須解決**：stable-baselines3 內部隨機性來源完整清單與 seed 注入點、torch deterministic 模式對效能的影響。
- [x] **II. 特徵可解釋性**：本 feature 不計算特徵（特徵屬 001），但訓練紀錄 MUST 含 reward 三項分量（log_return、drawdown_penalty、turnover_penalty）獨立曲線（FR-010），供 007 戰情室視覺化覆核 reward 設計合理性。
- [x] **III. 風險優先獎勵 (NON-NEGOTIABLE)**：本 feature 不修改 reward function（reward 在 003 env 內計算）；但訓練曲線 MUST 分別記錄三項 reward 分量（FR-010）以供 review。**禁止** PR 在訓練 wrapper 內偷加 reward shaping（憲法 III 明文要求）。
- [x] **IV. 微服務解耦**：FR-020 明文「本 feature 為純 Python package；不含 HTTP server、Kafka producer、資料庫連線」。FR-021 確保 `final_policy.zip` 為 stable-baselines3 標準格式，由 005 跨服務以「載入 checkpoint」消費，不共享 process 內存或 socket。
- [x] **V. 規格先行 (NON-NEGOTIABLE)**：本 plan 為 spec.md 通過 review 後之合規後續步驟。spec.md 含 23 條 FR、8 條 SC、4 個 user stories、6 個 edge cases，已通過 specification-quality validation。

**所有 gate 通過**，可進入 Phase 0。

## Project Structure

### Documentation (this feature)

```text
specs/004-ppo-training-loop/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli.md                       # CLI 介面契約
│   ├── training-config.schema.json  # yaml config JSON Schema
│   └── training-metadata.schema.json # metadata.json schema (FR-022)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/ppo_training/
├── __init__.py
├── __main__.py             # 支援 python -m ppo_training
├── cli.py                  # argparse + subcommand dispatch (train, compare)
├── config.py               # TrainingConfig dataclass + yaml loader + JSON Schema 驗證
├── trainer.py              # 核心訓練類別（包裝 sb3 PPO、處理 callback、artefact 寫出）
├── seeding.py              # 4 層 PRNG 同步（FR-017）
├── data_gate.py            # 啟動時 Parquet hash + package version 比對（FR-018, FR-019）
├── callbacks.py            # 自訂 sb3 callback：metrics.csv writer、NaN/Inf detector、checkpoint
├── aggregate.py            # 多 seed 聚合
├── compare.py              # ablation vs baseline 比較（含 Welch's t-test、Cohen's d）
└── artefacts.py            # 統一管理 run 目錄結構與檔名規約

tests/
├── contract/
│   ├── test_cli_contract.py
│   └── test_metadata_schema.py
├── integration/
│   ├── test_train_smoke.py
│   ├── test_multi_seed_aggregate.py
│   ├── test_resume_byte_identical.py
│   ├── test_data_hash_gate.py
│   └── test_nan_loss_abort.py
└── unit/
    ├── test_seeding.py
    ├── test_config_loader.py
    ├── test_aggregate.py
    ├── test_callbacks.py
    └── test_artefacts.py

configs/
├── baseline.yaml
├── ablation_no_smc.yaml
└── smoke.yaml
```

**Structure Decision**: 採 Single project layout（憲法 Tech Stack 允許之 Python 函式庫慣例）。`src/ppo_training/` 為唯一 package、CLI 透過 `python -m ppo_training` 進入。理由：本 feature 純函式庫 + CLI、無 web server / 前端、不需多 package 拆分。

## Complexity Tracking

> 無憲法違反項，本表為空。
