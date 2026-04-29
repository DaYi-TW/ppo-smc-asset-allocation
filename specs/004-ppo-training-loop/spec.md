# Feature Specification: PPO 訓練主迴圈（PPO Training Loop）

**Feature Branch**: `004-ppo-training-loop`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 PPO 訓練主迴圈，消費 003 PortfolioEnv 與 stable-baselines3 PPO 演算法，產出可推理之 policy checkpoint，並紀錄 reward 三項分量、訓練曲線、跨 seed 收斂統計，作為論文 Findings 章節之數據來源。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 跑通一次完整訓練（Priority: P1）

ML 研究者需要在已通過 003 env_checker 的環境上跑完一次完整 PPO 訓練，得到收斂之 policy checkpoint 與訓練曲線（episode return、reward 三項分量、policy loss、value loss、entropy、explained variance）。整個流程必須由單一 entrypoint 啟動，從 yaml config 讀取所有超參數，產生帶時間戳的 run 目錄（含 checkpoint、TensorBoard log、metadata、git commit hash）。

**Why this priority**: 沒有可跑通的訓練迴圈，論文 Findings 章節無法產出任何數據；對應憲法 Principle I「可重現性」之 RL 部分。

**Independent Test**: 以 fixed seed 跑 100k step 訓練，驗證：(a) 結束後 `runs/<timestamp>_<git_hash>/` 目錄含 `final_policy.zip`、`tensorboard/`、`config.yaml` (使用過的)、`metrics.csv`、`metadata.json`（含 git commit、Parquet hash、套件版本、訓練起訖 UTC 時間）。(b) `metrics.csv` 含每 1000 step 一列、欄位齊全。

**Acceptance Scenarios**:

1. **Given** 003 已實作完成、`data/raw/` 有 002 產出的 Parquet 快照，**When** 執行 `python -m ppo_training.cli train --config configs/baseline.yaml`，**Then** 訓練順利結束、最終 mean episode return 為 finite 數值、`runs/` 下出現完整 artefact 目錄。
2. **Given** 同上配置，**When** 中途 `Ctrl+C` 中斷，**Then** 系統 MUST 在收到 SIGINT 後安全寫出當前 checkpoint 並結束，不留下半損 artefact。

---

### User Story 2 - 跨 seed 收斂統計（Priority: P1）

論文需要證明訓練收斂不是單一 seed 的偶然結果。研究者要能以單一指令跑同 config × N 個 seed，自動聚合各 seed 之最終 mean return、Sharpe ratio、最大回撤，產出 mean ± std 統計表與收斂曲線（含 95% CI 區間）。

**Why this priority**: 對應憲法 Principle I「可重現性」與論文審稿一定會問的「結果是否 robust to random seed」。沒有跨 seed 統計，論文 Findings 章節缺乏統計嚴謹性。

**Independent Test**: 以 `--seeds 5` flag 跑 5 個 seed × 100k step，驗證 (a) 5 個 run 目錄都產生且 metadata 中 seed 各異、(b) 自動產出 `aggregate.csv` 與 `aggregate.png`（學習曲線含 mean ± std 帶狀區間）。

**Acceptance Scenarios**:

1. **Given** baseline.yaml 與 `--seeds 1,2,3,4,5`，**When** 執行訓練，**Then** 5 個 seed 的最終 mean episode return 以 mean ± std 形式寫入 `aggregate.csv`，相對標準差（CV = std/|mean|）≤ 0.5（指收斂穩定）。
2. **Given** 同上輸出，**When** 以同 commit 重跑同 5 seed，**Then** 每個 seed 對應之 `metrics.csv` byte-identical（FR-008 跨次重跑可重現）。

---

### User Story 3 - SMC ablation 對照訓練（Priority: P2）

論文 Findings 章節需要比較「含 SMC 特徵 vs. 純價格 baseline」之訓練成效，必須由相同訓練 entrypoint 在僅切換 `include_smc` 一個布林值的條件下產生兩條訓練曲線，其餘超參數、seed、資料快照完全一致。

**Why this priority**: 論文核心主張「SMC 特徵帶來增量價值」需要 ablation 對比佐證；對應憲法 Principle II（特徵可解釋性）的量化驗證面向。

**Independent Test**: `--config configs/ablation_no_smc.yaml --seeds 5` 與 `--config configs/baseline.yaml --seeds 5` 兩次 run，產出 `compare.csv` 比較最終 mean episode return、最終 NAV、最大回撤等三項指標的差異與 t-test p-value。

**Acceptance Scenarios**:

1. **Given** baseline 與 ablation 兩 config 僅在 `env.include_smc` 欄位不同，**When** 兩組訓練各跑 5 seed × 100k step、自動聚合，**Then** 產出之 `compare.csv` 含兩組之 mean ± std 與 Welch's t-test p-value。
2. **Given** 兩組訓練之 `metadata.json`，**When** 比對其 Parquet hash、git commit、PPO 超參數，**Then** 除 `env.include_smc` 外完全一致（diff tool 可機器驗證）。

---

### User Story 4 - 從 checkpoint 續訓（Priority: P3）

長訓練（>500k step）可能因機器重啟或其他中斷需從 checkpoint 續訓；研究者要能以 `--resume runs/<timestamp>_<hash>/checkpoint_step_50000.zip` 接續訓練，且續訓後的 trajectory 與一次跑完 byte-identical（容差 1e-6，因 PPO 內部 advantage normalization 涉及 batch 統計量，無法做到 1e-9）。

**Why this priority**: 訓練長度動輒數小時，無 checkpoint 機制將浪費資源；但相對 P1/P2，續訓不是論文核心主張，故為 P3。

**Independent Test**: A: 一次跑 100k step；B: 跑 50k step 後 SIGTERM、再 `--resume` 跑剩 50k step。比對 A 與 B 的最終 policy 在固定 100 個 obs 上的 action 輸出差異 ≤ 1e-6。

**Acceptance Scenarios**:

1. **Given** 已存在 `checkpoint_step_50000.zip` 與其對應之 `replay_buffer.pkl`、`prng_state.pkl`，**When** 以 `--resume` 啟動，**Then** 訓練從 step 50001 繼續、log 寫入同一 `metrics.csv` 末尾、TensorBoard 不出現重複 step。

---

### Edge Cases

- **配置與環境 hash 不符**：訓練啟動時 MUST 比對 `config.yaml` 中宣告之 `data_root` 對應 Parquet hash 與 002 metadata；不符 raise `RuntimeError("Data snapshot has changed since this config was authored")`，避免在污染資料上偷偷訓練。
- **GPU 不可用**：config 指定 `device=cuda` 但 CUDA 不可用 MUST raise 明確錯誤而非靜默退回 CPU（避免訓練速度失準導致超出預期 budget）。
- **訓練曲線 NaN/Inf**：偵測到 policy/value loss 為 NaN/Inf 時 MUST 立即停止訓練、保留當前 checkpoint、寫入 `metadata.json["abort_reason"] = "nan_loss_at_step_<N>"`，不靜默繼續。
- **磁碟空間不足**：寫 checkpoint 失敗時 MUST raise 並中止訓練，不得繼續訓練但漏寫 checkpoint。
- **單一 seed 退化解**：若某 seed 訓練結束時 mean episode return 比初始隨機策略還差（基準線由 003 隨機策略測得），MUST 於 `metadata.json["warnings"]` 中標示 `"degenerate_run"`，但不中止 aggregate 統計（讓使用者自行決定是否剔除）。
- **Replay buffer 過大**：on-policy PPO 預設 rollout buffer 約 2048 step × 7 維 obs ≈ 1 MB，安全；若使用者自行調大導致 > 1 GB MUST 在啟動時 warning。

## Requirements *(mandatory)*

### Functional Requirements

#### 訓練 entrypoint 與 CLI

- **FR-001**: 系統 MUST 提供 CLI `python -m ppo_training.cli train --config <yaml>`，從 yaml 讀取所有訓練超參數（PPO hyperparams、env config、seed、device、total_timesteps、checkpoint_freq、log_dir）。
- **FR-002**: CLI MUST 支援 `--seeds 1,2,3,4,5` 或 `--seeds 5`（後者展開為 1..5）以多 seed 平行/序列執行；多 seed 結束後自動產出 `aggregate.csv`、`aggregate.png`、`metadata_aggregate.json`。
- **FR-003**: CLI MUST 支援 `--resume <checkpoint_path>`，自動從 checkpoint 載入 policy、optimizer、replay buffer、PRNG state、step 計數。
- **FR-004**: CLI MUST 支援 `--device {cpu,cuda,auto}`，`auto` 等價於「有 cuda 用 cuda、否則 cpu」；明指 `cuda` 但 CUDA 不可用時 MUST raise（不退回 cpu）。
- **FR-005**: CLI MUST 支援 `--dry-run`：完整載入 config、建構 env 與 PPO 物件、跑 1 個 rollout（不更新 policy）、不寫任何 artefact，用於驗證 config 合法性與環境連通。

#### 配置與 artefact

- **FR-006**: 系統 MUST 接受之 yaml config 包含區塊：`env:` (對應 003 PortfolioEnvConfig 全部欄位)、`ppo:` (learning_rate、n_steps、batch_size、n_epochs、gamma、gae_lambda、clip_range、ent_coef、vf_coef、max_grad_norm、policy_kwargs)、`training:` (total_timesteps、seed、checkpoint_freq、eval_freq、device、log_dir)、`logging:` (tensorboard、wandb_project、metrics_csv_freq)。
- **FR-007**: 每次 run MUST 產生獨立目錄 `runs/<UTC_timestamp>_<git_hash>_seed<N>/`（時間戳格式 `YYYYMMDD_HHMMSS`、git_hash 取 short 7 字元），內含 `config.yaml` (用過的 resolved 版本)、`final_policy.zip`、`checkpoint_step_*.zip`、`tensorboard/events.out.*`、`metrics.csv`、`metadata.json`、`stdout.log`、`stderr.log`。
- **FR-008**: `metadata.json` MUST 含：`git_commit_hash`、`git_dirty: bool`、`utc_start`、`utc_end`、`duration_seconds`、`hostname`、`python_version`、`package_versions`（dict 含 numpy、pandas、gymnasium、stable-baselines3、pytorch）、`data_hashes`（從 003 env 取得）、`seed`、`total_timesteps`、`final_mean_episode_return`、`abort_reason: str | null`、`warnings: list[str]`。
- **FR-009**: 在相同 commit、相同 Parquet hash、相同 seed、相同 config 下重跑訓練，`metrics.csv` byte-identical（容差 0.0；浮點寫出採固定 18 位有效數字）。

#### 訓練曲線與監控

- **FR-010**: `metrics.csv` MUST 每 `metrics_csv_freq`（預設 1000）step 寫一列，欄位至少含：`step`、`mean_episode_return`、`mean_episode_length`、`mean_log_return`、`mean_drawdown_penalty`、`mean_turnover_penalty`、`policy_loss`、`value_loss`、`entropy`、`approx_kl`、`explained_variance`、`learning_rate`、`fps`。
- **FR-011**: TensorBoard log MUST 包含上述全部 metric 之 scalar 曲線；額外加 histogram：每 10k step 紀錄 policy 對固定 fixed eval batch 的 action 分佈、weights 分佈。
- **FR-012**: 系統 MUST 每 `checkpoint_freq`（預設 50000）step 存一次 checkpoint（policy、optimizer、replay buffer、PRNG state），且最終必存一次 `final_policy.zip`。
- **FR-013**: 系統 MUST 偵測 NaN/Inf loss、退化解（最終 return 比隨機策略基準還差）、replay buffer 異常、磁碟寫入失敗，分別於 `metadata.json["abort_reason"]` 或 `["warnings"]` 紀錄。

#### 多 seed 聚合

- **FR-014**: 多 seed 結束後系統 MUST 自動產出聚合報告：`aggregate.csv`（每 step 對應之 mean、std、min、max across seeds）、`aggregate.png`（mean line + std band）、`metadata_aggregate.json`（含各 seed 之最終 metric 與 Welch's t-test p-value 對比 baseline，如有）。
- **FR-015**: 系統 MUST 支援 `--compare-baseline runs/<baseline_aggregate_dir>` flag：在 ablation 訓練結束後自動 vs. 既有 baseline aggregate 計算 p-value、effect size（Cohen's d）並寫入 `compare.csv`。
- **FR-016**: 跨 seed aggregate 計算 MUST 為 deterministic：相同 5 個 seed 的 metrics.csv 經兩次 aggregate 結果 byte-identical。

#### 可重現性

- **FR-017**: 所有 PRNG 來源 MUST 由 config `training.seed` 同步：(a) 003 env 的 4 層 seed (research R1)、(b) PyTorch CPU & CUDA seed、(c) numpy global seed（僅供 stable-baselines3 內部使用、本 feature 自身仍走 `np.random.default_rng(seed)`）、(d) Python `random` 全域。
- **FR-018**: 訓練啟動時 MUST 寫入 `metadata.json` 套件版本指紋；任何 package 版本與 yaml 中宣告之 `expected_versions:` 區塊不符 MUST 於非 `--force-version-mismatch` 時 raise。
- **FR-019**: 訓練啟動時 MUST 比對 `data_root` 之 Parquet metadata 雜湊與 yaml 內 `expected_data_hashes:` 區塊；不符 raise（避免在污染資料上訓練）。

#### 跨層介面

- **FR-020**: 本 feature MUST 為純 Python package；不含 HTTP server、Kafka producer、資料庫連線（後者屬 005-006 features）。輸出 artefact 為 005 推理服務之輸入。
- **FR-021**: `final_policy.zip` MUST 為 stable-baselines3 標準格式，可由 `PPO.load(path)` 直接載入；005 推理服務將以此格式消費。
- **FR-022**: `metadata.json` MUST 為 JSON-serializable，schema 由 `contracts/training-metadata.schema.json` 規範（Phase 1 產出），便於 005/007 機器讀取。

#### 不在範圍內

- **FR-023**: 本 feature **不**做：超參數搜尋（hyperparameter tuning，留給未來 feature）、模型壓縮/蒸餾、多 GPU 分散式訓練、推理時的部署封裝（005 範圍）。

### Key Entities

- **TrainingRun**: 一次訓練之完整紀錄。屬性：seed、git_commit、utc_start/end、artefact 目錄、最終 metric、abort_reason。
- **TrainingConfig**: 結構化 yaml 配置。包含 env (對應 003)、ppo（hyperparams）、training（seed、device 等）、logging 四區塊。
- **MetricsRow**: `metrics.csv` 一列；step + 12 個 metric 欄位。
- **CheckpointArtefact**: `policy.zip` + `optimizer.pkl` + `replay_buffer.pkl` + `prng_state.pkl` + `step_count.txt` 之集合。
- **AggregateReport**: 跨 seed 聚合輸出。`aggregate.csv` + `aggregate.png` + `metadata_aggregate.json`。
- **ComparisonReport**: ablation vs. baseline 之 t-test 與 effect size 報告。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 在配備 stable-baselines3 PPO 預設超參數、100k total_timesteps、單一 seed、CPU 模式下，完整訓練 + artefact 寫出耗時 < 30 分鐘（單機 CPU）。GPU 模式 < 10 分鐘。
- **SC-002**: 5 個不同 seed 跑同 config × 100k step 後，最終 mean episode return 之相對標準差（CV）≤ 0.5（收斂穩定）。
- **SC-003**: 同 commit、同 seed、同 config 重跑訓練，`metrics.csv` byte-identical（容差 0.0）。
- **SC-004**: SMC ablation 對比 baseline，含 SMC 之最終 mean episode return 高於純價格版本，且 Welch's t-test p-value < 0.05（5 seed × 100k step 規模）。
- **SC-005**: `--resume` 從 checkpoint 續訓得到之最終 policy 與一次跑完版本的固定 100 個 obs action 輸出差異 ≤ 1e-6。
- **SC-006**: 單元 + 整合測試覆蓋率 ≥ 85%（PPO 訓練 wrapper 邏輯，不含 stable-baselines3 內部）。
- **SC-007**: NaN/Inf loss 偵測之 false negative rate = 0（一旦發生必中止），false positive rate < 1%（不誤殺正常訓練）。
- **SC-008**: 訓練啟動時資料 hash 比對失敗的錯誤訊息能讓使用者在不讀原始碼的情況下定位問題（明示哪個資產 hash 不符、預期值、實際值）。

## Assumptions

- 003 PortfolioEnv 已實作完成、env_checker 通過、跨平台 byte-identical（FR-020、SC-002）。
- 002 已產出 `data/raw/` 下全部 Parquet 快照與 metadata sidecar。
- 訓練主要在單機 CPU 上跑（典型 100k step、單 seed < 30 分鐘）；GPU 為加速選項，不是必需。
- stable-baselines3 ~= 2.3 為 PPO 實作來源；其 API 穩定性由其官方語義版本承諾保證。
- TensorBoard 為視覺化工具預設選項；wandb 為可選整合，不作為必需。
- 訓練長度典型範圍 100k–1M step；超出此範圍的 long-horizon training 不在本 feature 規劃內。
- 多 seed 數量典型 3–10；> 10 seed 屬論文最終實驗階段，使用者自行平行調度（cluster scheduling 不在本 feature 範圍）。
- 跨 seed aggregate 採簡單 mean ± std + Welch's t-test，不做 bootstrap CI / Bayesian credible interval（後者留給未來統計分析 feature）。
