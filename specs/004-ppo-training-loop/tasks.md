---

description: "Task list for 004-ppo-training-loop implementation"
---

# Tasks: PPO Training Loop

**Input**: Design documents from `/specs/004-ppo-training-loop/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are required per憲法 Principle V + spec SC-006（覆蓋率 ≥ 85%）。

**Organization**: Tasks 依 user story 分組。

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

- Single project: `src/ppo_training/`、`tests/`、`configs/` 於 repo root。

---

## Phase 1: Setup

- [ ] T001 建立 `src/ppo_training/` package 結構（含 `__init__.py`、`__main__.py`）
- [ ] T002 於 `pyproject.toml` 增加 `[project.optional-dependencies]` `train = ["stable-baselines3>=2.3,<3", "tensorboard", "scipy", "matplotlib", "PyYAML", "jsonschema"]`
- [ ] T003 [P] 建立 `configs/baseline.yaml`、`configs/ablation_no_smc.yaml`、`configs/smoke.yaml` 範例配置（依 quickstart.md）
- [ ] T004 [P] 於 `pyproject.toml` 加入 `[tool.pytest.ini_options]` `testpaths = ["tests"]`、`addopts = "--strict-markers --strict-config"`、`markers = ["integration", "contract", "slow"]`

---

## Phase 2: Foundational (Blocking)

**Purpose**: PRNG 同步、資料 gate、artefact 結構為所有 user stories 之基礎。

**⚠️ CRITICAL**: 此階段未完成、不得開始任何 user story。

- [ ] T005 實作 `src/ppo_training/seeding.py`：`set_global_seeds(seed: int, device: str) -> None` 同步 4 層 PRNG（Python random、numpy global、torch CPU、torch CUDA）+ `torch.use_deterministic_algorithms(True)`、`os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'`（依 research R1）
- [ ] T006 [P] 實作 `src/ppo_training/artefacts.py`：`RunPaths` dataclass + `make_run_id(seed, git_hash, dirty) -> str`（格式 `YYYYMMDD_HHMMSS_<hash7>{-dirty}_seed<N>`，依 data-model §2）
- [ ] T007 [P] 實作 `src/ppo_training/config.py`：`TrainingConfig` dataclass（依 data-model §1）+ `load_config(path: Path) -> TrainingConfig`（yaml 載入 → JSON Schema 驗證 → dataclass 反序列化 → 自訂規則驗證）
- [ ] T008 實作 `src/ppo_training/data_gate.py`：`verify_data_hashes(config) -> None`（依 research R10 錯誤訊息規範）+ `verify_package_versions(config, force: bool) -> None`
- [ ] T009 [P] 實作 `src/ppo_training/cli.py` 骨架：argparse + subcommand dispatch（`train`、`compare`），尚不接通 trainer
- [ ] T010 [P] 撰寫單元測試 `tests/unit/test_seeding.py`：驗證 4 層 PRNG 設定後 `np.random.rand()`、`torch.rand(1)`、`random.random()` 三次呼叫 byte-identical
- [ ] T011 [P] 撰寫單元測試 `tests/unit/test_config_loader.py`：合法 yaml 通過、缺欄位 raise、型別錯誤 raise、hash pattern 不符 raise；含 fixture（baseline.yaml、smoke.yaml、無效 yaml）
- [ ] T012 [P] 撰寫單元測試 `tests/unit/test_artefacts.py`：`make_run_id` 格式正確、`RunPaths` 各路徑正確
- [ ] T013 撰寫整合測試 `tests/integration/test_data_hash_gate.py`：fixture 提供假 `data/raw/metadata.json`、yaml 含不符 hash → raise `DataSnapshotMismatchError` 且訊息含 asset 名、預期 hash 前 12 字元

**Checkpoint**: Foundation 完成，可開始 user stories。

---

## Phase 3: User Story 1 - 跑通一次完整訓練 (Priority: P1) 🎯 MVP

**Goal**: 單 seed PPO 訓練、產出 `runs/<run_id>/` 完整 artefact。

**Independent Test**: 跑 100k step CPU smoke、檢查 6 個 artefact 檔案存在且結構正確。

### Tests for User Story 1

- [ ] T014 [P] [US1] 撰寫 contract test `tests/contract/test_cli_contract.py::test_train_subcommand_exit_codes`：驗證 `--config invalid.yaml` exit 2、`--device cuda`（無 GPU）exit 5、`--dry-run` exit 0 不寫 artefact
- [ ] T015 [P] [US1] 撰寫 contract test `tests/contract/test_metadata_schema.py`：載入 fixture metadata.json、用 `jsonschema.validate` 對 `contracts/training-metadata.schema.json` 驗證
- [ ] T016 [P] [US1] 撰寫整合測試 `tests/integration/test_train_smoke.py`：smoke.yaml × seed=1 × 256 step、驗證 (a) `runs/<run_id>/` 存在 (b) 6 個檔案存在 (c) `metrics.csv` ≥ 4 列 (d) `metadata.json` schema 通過

### Implementation for User Story 1

- [ ] T017 [US1] 實作 `src/ppo_training/callbacks.py`：`MetricsCSVCallback(BaseCallback)` 每 `metrics_csv_freq` step 寫一列；採 pandas `to_csv(float_format='%.18g', lineterminator='\n', mode='a')`（依 research R2）
- [ ] T018 [US1] 實作 `src/ppo_training/callbacks.py`：`NanInfDetectorCallback(BaseCallback)` 偵測 policy_loss / value_loss NaN/Inf 即 raise `NanLossDetectedError(step, metric)`（依 research R3）
- [ ] T019 [US1] 實作 `src/ppo_training/callbacks.py`：`CheckpointCallback(BaseCallback)` 每 `checkpoint_freq` step 寫 `<run_dir>/checkpoint_step_{step}.zip` + `replay_buffer.pkl` + `prng_state.pkl`
- [ ] T020 [US1] 實作 `src/ppo_training/trainer.py`：`Trainer` 類別含 `__init__(config, run_paths)`、`fit() -> TrainingMetadata`、`_build_env()`（呼叫 003 PortfolioEnv）、`_build_model()`（sb3 PPO with seed）、`_register_callbacks()`、`_write_metadata(abort_reason, warnings)`
- [ ] T021 [US1] 接通 `cli.py` `train` subcommand → `Trainer.fit()`；處理 SIGINT（signal handler 寫 abort_reason="sigint_at_step_N" 後 exit 130）
- [ ] T022 [US1] 處理錯誤 → exit code 對應（contract 表）：`ConfigValidationError` exit 2、`DataSnapshotMismatchError` exit 3、`PackageVersionMismatchError` exit 4、`CudaUnavailableError` exit 5、`NanLossDetectedError` exit 6、`OSError`(disk full) exit 7
- [ ] T023 [US1] 增加 `Trainer._write_metadata` 內含完整 13 個欄位（依 data-model §4 + schema）；`config_sha256` 由 resolved config.yaml 內容計算
- [ ] T024 [US1] 增加 reward 三項分量曲線到 `metrics.csv`：自訂 `RewardComponentTracker` callback 從 env info dict 取 `log_return / drawdown_penalty / turnover_penalty`，每 episode 結束後 累積 last-100 平均

**Checkpoint**: US1 完成 — 單 seed 訓練能產出完整 artefact。

---

## Phase 4: User Story 2 - 跨 seed 收斂統計 (Priority: P1)

**Goal**: 多 seed 訓練自動聚合產出 aggregate.csv / .png / metadata_aggregate.json。

**Independent Test**: `--seeds 3` × smoke.yaml、驗證 3 個 run 目錄 + 1 個 aggregate 目錄。

### Tests for User Story 2

- [ ] T025 [P] [US2] 撰寫單元測試 `tests/unit/test_aggregate.py`：3 個假 metrics.csv → `aggregate(...)` → 驗證 `aggregate.csv` mean/std 數值正確、`ci95` 用 scipy t.interval 計算、欄位完整
- [ ] T026 [P] [US2] 撰寫整合測試 `tests/integration/test_multi_seed_aggregate.py`：smoke.yaml × `--seeds 1,2,3`、驗證 3 個 run + 1 個 aggregate 目錄、`metadata_aggregate.json` 含 3 個 run_id 與 CV 數值

### Implementation for User Story 2

- [ ] T027 [P] [US2] 實作 `src/ppo_training/aggregate.py`：`aggregate_runs(run_paths: list[Path]) -> AggregateReport`，輸出 `aggregate.csv`（73 欄，依 data-model §5）、`metadata_aggregate.json`、`aggregate.png`（matplotlib：mean line + std band）
- [ ] T028 [US2] 接通 `cli.py` `train` subcommand 的 `--seeds 1,2,3,4,5` 序列執行邏輯：依序呼叫 Trainer.fit()、每個 seed 獨立 RunPaths；全部完成後呼叫 `aggregate_runs([...])`
- [ ] T029 [US2] 增加 `--seeds N` 與 `--seeds-expand` 解析邏輯到 cli.py（依 contract）
- [ ] T030 [US2] 確保 aggregate 計算 byte-identical（FR-016）：seed 列表先排序、`pd.concat` 後 `sort_values('step')`、輸出採同 R2 浮點格式

**Checkpoint**: US2 完成 — 多 seed 自動聚合可用。

---

## Phase 5: User Story 3 - SMC ablation 對照訓練 (Priority: P2)

**Goal**: ablation vs baseline 自動比較產出 compare.csv（含 Welch's t-test、Cohen's d）。

**Independent Test**: 跑 ablation 帶 `--compare-baseline`、驗證 `compare.csv` 含 9 欄、p_value 為 finite 數值。

### Tests for User Story 3

- [ ] T031 [P] [US3] 撰寫單元測試 `tests/unit/test_compare.py`：兩組 fake aggregate.csv → `compare(...)` → 驗證 t_statistic、p_value、cohens_d 與 scipy 直接呼叫結果一致；effect_size_label 對應 Cohen 1988 門檻（small <0.5、medium 0.5-0.8、large ≥0.8）
- [ ] T032 [P] [US3] 撰寫整合測試 `tests/integration/test_ablation_compare.py`：跑 baseline 2 seed → 跑 ablation 2 seed with `--compare-baseline`、驗證 `compare.csv` 存在且 schema 正確

### Implementation for User Story 3

- [ ] T033 [P] [US3] 實作 `src/ppo_training/compare.py`：`compare_aggregates(baseline_dir, ablation_dir, output_path) -> Path`、Welch's t-test 採 `scipy.stats.ttest_ind(equal_var=False)`、Cohen's d 採 pooled std 公式
- [ ] T034 [US3] 實作 `compare` subcommand 於 cli.py（獨立執行用）
- [ ] T035 [US3] 接通 train subcommand 的 `--compare-baseline` flag：訓練 + aggregate 完成後自動呼叫 `compare_aggregates`
- [ ] T036 [US3] 撰寫 `configs/ablation_no_smc.yaml`：`env.include_smc: false`，其餘與 baseline 完全一致（測試可機器 diff 出僅此一處差異）

**Checkpoint**: US3 完成 — SMC ablation 對比論文 Findings 章節可用。

---

## Phase 6: User Story 4 - 從 checkpoint 續訓 (Priority: P3)

**Goal**: `--resume <ckpt>` 從中斷點續訓、最終 policy 對固定 obs 之 action 差異 ≤ 1e-6。

**Independent Test**: 跑 1k step 中斷 → resume 跑剩 1k step；vs 一次跑 2k step；100 obs 上 |action_diff| ≤ 1e-6。

### Tests for User Story 4

- [ ] T037 [P] [US4] 撰寫整合測試 `tests/integration/test_resume_byte_identical.py`：A 一次跑 2k step；B 跑 1k step、SIGTERM、`--resume` 跑剩 1k step；100 obs deterministic action max(|diff|) ≤ 1e-6（SC-005）

### Implementation for User Story 4

- [ ] T038 [US4] 實作 `Trainer._save_checkpoint(step)`：寫 `checkpoint_step_{step}.zip`（policy）+ `replay_buffer.pkl`（rollout buffer）+ `prng_state.pkl`（4 層 PRNG snapshot via PRNGState 序列化）+ `step_count.txt`
- [ ] T039 [US4] 實作 `Trainer._resume_from_checkpoint(ckpt_path)`：載入上述 4 個檔案、PPO.load + 還原 PRNG + step counter；驗證 ckpt 同目錄之 config.yaml 與當前 config 一致（git_commit_hash + config_sha256）
- [ ] T040 [US4] 接通 `--resume` flag 到 cli.py：偵測 `--resume` → 跳過 fresh init、改呼叫 `_resume_from_checkpoint`；metrics.csv 採 `mode='a'` append（不寫新 header）

**Checkpoint**: US4 完成 — 續訓功能可用。

---

## Phase 7: Polish & Cross-Cutting

- [ ] T041 [P] 撰寫單元測試 `tests/unit/test_callbacks.py`：分別驗證 MetricsCSVCallback 寫出格式、NanInfDetectorCallback 偵測時序、CheckpointCallback 寫出檔案完整
- [ ] T042 [P] 撰寫整合測試 `tests/integration/test_nan_loss_abort.py`：monkeypatch sb3 logger 在 step=128 注入 NaN policy_loss、驗證訓練於 step ≤ 256 中止、metadata.json["abort_reason"] = "nan_loss_at_step_128"、final_policy.zip 仍存在
- [ ] T043 跨平台驗證：於 Linux + Windows 各跑 smoke.yaml × seed=1，比對 metrics.csv byte-identical（SC-003）
- [ ] T044 [P] 撰寫 quickstart 對應的 manual smoke：依 quickstart.md 從零執行、驗證 5-min smoke 流程能跑通、產出符合 quickstart 描述
- [ ] T045 設定 GitHub Actions CI：跑 lint（ruff）+ typecheck（mypy）+ pytest（含 coverage gate ≥ 85%）；matrix Python 3.11、3.12
- [ ] T046 [P] 撰寫 README 章節 `## Training`（連結至 quickstart.md）
- [ ] T047 程式碼覆蓋率審視：`pytest --cov=src/ppo_training --cov-report=html` → 補不足 ≥ 85% 之 module 測試
- [ ] T048 性能驗證：100k step CPU smoke、確認 < 30 min（SC-001）；若超出，檢查 torch deterministic 開銷
- [ ] T049 GPU 路徑驗證（若本機有 NVIDIA GPU）：CUDA mode 跑 smoke、metrics.csv 與 CPU 不要求 byte-identical（GPU vs CPU 浮點不同），但 final policy 行為應合理

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup（Phase 1）→ Foundational（Phase 2）→ User Stories（Phase 3-6）→ Polish（Phase 7）
- US1 為 MVP；US2 依賴 US1（aggregate 需 metrics.csv）；US3 依賴 US2（compare 需 aggregate.csv）；US4 依賴 US1（resume 需 checkpoint）。

### Within Each User Story

- Tests 先寫且 FAIL（TDD）→ implementation
- callbacks 先（pure）→ trainer 後（orchestrator）
- CLI 接通最後

### Parallel Opportunities

- T003、T004、T006、T007、T009、T010、T011、T012：Phase 1-2 內可平行（不同檔案、無互相依賴）
- T014、T015、T016：US1 tests 可平行（不同檔案）
- T025、T026 平行；T031、T032 平行
- T041、T042 平行；T046 與其他 polish 平行

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 → Phase 2 → Phase 3 (US1)
2. **STOP and VALIDATE**: smoke.yaml 跑通、artefact 完整
3. 此時即可開始實 002 + 003 整合除錯

### Incremental Delivery

1. MVP (US1) → 跑 baseline 單 seed
2. + US2 → 跑 baseline 5 seed、有聚合報告
3. + US3 → ablation vs baseline、論文 Findings 主數據可用
4. + US4 → 長訓練可斷點續做
5. Polish → CI、跨平台、性能驗證

---

## Notes

- 每個 task 完成後立即 commit
- 違反憲法 I（reproducibility）的 PR 一律拒絕：metrics.csv byte-identical 是 hard gate
- US3 的 ablation_no_smc.yaml 與 baseline.yaml 必須僅在 `env.include_smc` 一個欄位差異（測試 T036 機器驗證）
- 不要在 trainer.py 內偷加 reward shaping（憲法 III NON-NEGOTIABLE）
