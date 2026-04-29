---
description: "Task list for 003-ppo-training-env"
---

# Tasks: PPO 訓練環境（PPO Training Environment）

**Input**: Design documents from `/specs/003-ppo-training-env/`
**Prerequisites**: plan.md (✅), spec.md (✅), research.md (✅), data-model.md (✅), contracts/api.pyi (✅), contracts/info-schema.json (✅), quickstart.md (✅)

**Tests**: 本 feature 明確要求測試（憲法 SC-006 ≥ 90% 覆蓋率、SC-003 `env_checker` 通過、SC-002 跨平台 byte-identical）。所有測試任務皆**必須**包含並依 TDD 流程先寫測試後實作。

**Organization**: 任務以 user story 為主軸組織；US1（隨機 episode）為 MVP，其他 US 在 Foundational 完成後可並行。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔、無相互依賴）
- **[Story]**: US1 / US2 / US3 / US4，對應 spec.md 的四個 user story
- 描述含完整檔案路徑

## Path Conventions

- Single project：`src/portfolio_env/`、`tests/{contract,integration,unit}/`
- 與 001-smc-feature-engine、002-data-ingestion 同 monorepo（`src/smc_features/`、`src/data_ingestion/` 並列）

---

## Phase 1: Setup（共用基礎設施）

**Purpose**: 建立 portfolio_env package 骨架、依賴鎖定、CI 跨平台矩陣設定。

- [ ] T001 在 `pyproject.toml` 新增 `portfolio_env` package（位於 `src/portfolio_env/`）並 pin 依賴：`gymnasium ~= 0.29`、`numpy ~= 1.26`、`pandas >= 2.0`、`pyarrow >= 14`（透傳 002）；dev 依賴：`pytest`、`pytest-cov`、`jsonschema`（用於 contracts/info-schema.json 驗證）。引用 plan.md Technical Context 的版本鎖定策略。
- [ ] T002 [P] 建立 `src/portfolio_env/` 目錄與九個空模組：`__init__.py`、`config.py`、`env.py`、`data_loader.py`、`observation.py`、`action.py`、`reward.py`、`seeding.py`、`info.py`、`render.py`（plan.md Source Code 章節對齊）。
- [ ] T003 [P] 建立 `tests/contract/`、`tests/integration/`、`tests/unit/` 三層目錄，每層放 `__init__.py` 與 `conftest.py`（先空檔，T009 再寫共用 fixture）。
- [ ] T004 [P] 在 CI 設定（`.github/workflows/test.yml` 或既有檔）加入環境變數 `OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`，並擴充矩陣為 `{ubuntu-latest, macos-latest, windows-latest} × {python-3.11, python-3.12}`，以支援 SC-002 跨平台 byte-identical 驗證（research R2）。
- [ ] T005 [P] 在 `.editorconfig` 與 `pyproject.toml [tool.ruff]` 設定 lint 規則（line-length=100、isort、E、F、W、B）；新增 `pre-commit` hook 鎖 `ruff check` + `ruff format`。

---

## Phase 2: Foundational（阻塞性前置任務）

**Purpose**: 所有 user story 共同依賴的核心基礎建設。**必須**全部完成才能進入 Phase 3+。

**⚠️ CRITICAL**: 沒有完成 Phase 2 不得開始任何 US 的實作任務。

### 配置 dataclass

- [ ] T006 在 `src/portfolio_env/config.py` 實作 `RewardConfig`（frozen dataclass）與 `PortfolioEnvConfig`（frozen dataclass）兩個類別，欄位與不變式驗證（`__post_init__`）對齊 data-model.md §2.1、§2.2；`PortfolioEnvConfig` 必須含 `render_mode: str | None = None`（FR-027、Gymnasium 0.29+）；`SMCParams` 改以 `from smc_features import SMCParams` re-export，不重宣告。
- [ ] T007 [P] 在 `tests/unit/test_config.py` 撰寫 RewardConfig / PortfolioEnvConfig 的單元測試：(a) frozen 不可變、(b) `__post_init__` 對 `lambda_mdd < 0`、`position_cap > 1`、`position_cap × len(assets) < 1`、`initial_nav <= 0`、`base_slippage_bps < 0`、`render_mode not in (None, "ansi")` 皆 raise `ValueError`、(c) 預設值符合 spec FR-007 / FR-022 / FR-023。

### 公開 API 對齊與測試

- [ ] T008 在 `src/portfolio_env/__init__.py` 依 `contracts/api.pyi` 的 `__all__` 列表 re-export `PortfolioEnv`、`PortfolioEnvConfig`、`RewardConfig`、`SMCParams`、`info_to_json_safe`、`make_default_env`（部分符號於後續任務實作；先以 import 失敗時 raise `NotImplementedError` 的占位填空）。
- [ ] T009 在 `tests/conftest.py`（repo 根層） 寫共用 fixture：(a) `tmp_data_root` 產生 6 檔股票 + DTB3 的 mini Parquet（10 列） + sidecar metadata，方便 unit/integration 測試在不依賴 002 真實快照下跑；(b) `default_config` 回傳 `PortfolioEnvConfig(data_root=tmp_data_root)`；(c) `set_blas_single_thread` autouse fixture 設 `OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`（強化測試 deterministic）。
- [ ] T010 [P] 在 `tests/contract/test_public_api.py` 撰寫 contract test：以 `importlib` + `inspect` 驗證 runtime `portfolio_env` 模組的公開符號簽章與 `contracts/api.pyi` 完全一致（symbol set、function signature、`PortfolioEnvConfig` 欄位順序與型別 annotation）；引用 plan.md「公開 API 約 6 個 symbol」原則。

### 四層 seed 同步

- [ ] T011 在 `src/portfolio_env/seeding.py` 實作 `synchronize_seeds(env, seed)` 工具函式：依 research R1 步驟同步 `super().reset(seed=seed)` 取出的 `env.np_random`、新建 `env._py_random = random.Random(seed)`、`env._numpy_rng = numpy.random.default_rng(seed)`，並斷言不觸碰 `numpy.random` 全域 / `random` 全域 / `os.urandom`。
- [ ] T012 [P] 在 `tests/unit/test_seeding.py` 撰寫單元測試：(a) 兩次呼叫 `synchronize_seeds(env, 42)` 後從 `env._numpy_rng.random(100)` 取出之數列相同；(b) `synchronize_seeds` 後再呼叫 `numpy.random.random()` 全域，其輸出**不**等於 `env._numpy_rng.random()`（證明全域 PRNG 未被污染）；(c) seed=None 時不 raise（依 Gymnasium 慣例為 non-reproducible 模式）。

### 資料載入與 hash 比對

- [ ] T013 在 `src/portfolio_env/data_loader.py` 實作 `load_environment_data(config) -> EnvData` namedtuple-like 結構，內部步驟：(1) 對 6 檔股票 `data_ingestion.loader.load_asset_snapshot(ticker)` + 對 DTB3 `load_rate_snapshot()`；(2) 對每檔資產讀取 sidecar metadata，立即重新計算 SHA-256 並比對；不符則 `raise RuntimeError("Snapshot hash mismatch: {asset} expected {x}, got {y}")` （FR-021、research R6）；(3) 過濾 `quality_flag != ok` 的股票交易日（取交集後 `_trading_days`）；(4) FRED `quality_flag == "missing_rate"` 對 `rate_pct` 做 forward fill（research R5）；(5) 回傳結構含 `_trading_days`、`_closes`、`_returns`（simple return）、`_rf_daily`、`_data_hashes`。
- [ ] T014 [P] 在 `tests/integration/test_data_hash_mismatch.py` 撰寫 integration test：建立一份合法 Parquet + 故意改一個 byte 的副本，驗證 `PortfolioEnv(config)` 立即 raise `RuntimeError` 並訊息含「Snapshot hash mismatch」與資產名（FR-021）。
- [ ] T015 [P] 在 `tests/unit/test_data_loader.py` 撰寫單元測試：(a) FRED `missing_rate` 觸發 forward fill 後該日 `rate_pct` 等於前一可用值；(b) 任一股票 `quality_flag != ok` 該日從 `_trading_days` 剔除、`_skipped_dates` 累積；(c) `_returns` 為 simple return（`close_t / close_{t-1} − 1`，t=0 列為 0），非 log return；(d) `_rf_daily` 公式 `(1 + rate_pct/100)^(1/252) − 1`。

### SMC 預計算

- [ ] T016 在 `src/portfolio_env/data_loader.py` 擴充 `load_environment_data`：若 `config.include_smc=True`，於資料載入後立即呼叫 `smc_features.batch_compute(df, params=config.smc_params)` 為每檔股票計算 SMC 5 欄；結果以 `dict[ticker, np.ndarray[float32]]`（shape `(T, 5)`）存於 `EnvData._smc_features`；依 FR-010a 將 `bos_signal`/`choch_signal`（int8）轉 float32 ∈ {-1.0, 0.0, 1.0}、`ob_touched`（bool）轉 float32 ∈ {0.0, 1.0}、`fvg_distance_pct` / `ob_distance_ratio`（float64）轉 float32（NaN 暫不替換，留待 observation 組裝時記在 `nan_replaced` 計數）。
- [ ] T017 [P] 在 `tests/unit/test_smc_precompute.py` 驗證：(a) `include_smc=True` 時 `_smc_features[ticker].shape == (T, 5)`、dtype float32；(b) 五欄編碼符合 FR-010a；(c) `include_smc=False` 時 `_smc_features is None`；(d) `batch_compute` 只被呼叫一次（用 `unittest.mock.patch` + `assert_called_once`）。

### 觀測組裝與動作處理

- [ ] T018 在 `src/portfolio_env/observation.py` 實作 `build_observation(env_data, current_index, current_weights, include_smc) -> np.ndarray[float32]`：依 data-model.md §3.1.1~§3.1.4 順序填入 zeros buffer（`include_smc=True`→ shape (63,)；`include_smc=False`→ shape (33,)）；`t < 20` 時 backfill 用 `t=0` 值；NaN 一律替換為 0.0 並回傳替換次數供 info 累計（FR-012）。輸出 `numpy.zeros(D, dtype=float32)` 後分區 in-place 寫入，避免 `numpy.concatenate`（research R2）。
- [ ] T019 [P] 在 `tests/unit/test_observation_layout.py` 撰寫單元測試：(a) `include_smc=True` shape=(63,)、`include_smc=False` shape=(33,)；(b) 兩種 config 下 `obs[0:24]`（價格）byte-identical、`obs[54:56]/obs[24:26]`（macro）對應、`obs[56:63]/obs[26:33]`（weights）對應；(c) NaN 替換次數正確；(d) `bos_signal`、`choch_signal` 編碼 ∈ {-1.0, 0.0, 1.0}、`ob_touched` ∈ {0.0, 1.0}（FR-010a）。
- [ ] T020 在 `src/portfolio_env/action.py` 實作 `process_action(action, prev_weights, position_cap) -> ProcessedAction` namedtuple，含三道處理（data-model.md §4）：(1) NaN 檢查 raise；(2) L1 normalize（容差 1e-6；`sum < 1e-6` raise）；(3) water-filling position cap（research R9、data-model.md §4 step 3）；同步回傳 `action_renormalized: bool`、`position_capped: bool` 旗標。
- [ ] T021 [P] 在 `tests/unit/test_action_processing.py` 撰寫單元測試：(a) `[NaN, 0, ...]` 觸發 `ValueError("Action contains NaN")`；(b) `[0]*7` 或近零向量觸發 `ValueError("Action sum near zero")`；(c) `[0.5, 0.5, 0, 0, 0, 0, 0]` sum=1，不觸發 normalize；(d) `[1, 1, 0, 0, 0, 0, 0]` 觸發 normalize → `[0.5, 0.5, 0, ...]`、`action_renormalized=True`；(e) `[0.6, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05]` 觸發 cap → max <= 0.4、`position_capped=True`、sum 仍 == 1；(f) cash 不受 cap 限制（`[0, 0, 0, 0, 0, 0, 1]` 合法）；(g) water-filling 對多檔同時 > cap 的情境（`[0.5, 0.5, 0, 0, 0, 0, 0]`）正確收斂、單趟結束。

### Reward 計算

- [ ] T022 在 `src/portfolio_env/reward.py` 實作 `compute_reward_components(prev_nav, nav, peak_nav, prev_weights, weights, lambda_mdd, lambda_turnover) -> RewardComponents` namedtuple：(a) `log_return = numpy.log(nav / prev_nav)`；首步 `is_initial_step=True` 強制 0（FR-006、edge case）；(b) `drawdown_t = max(0.0, (peak_t - nav) / peak_t)`；(c) `turnover_t = 0.5 * numpy.sum(numpy.abs(weights - prev_weights))`；(d) `reward = log_return − lambda_mdd × drawdown − lambda_turnover × turnover`，以 Python `−` 字面順序組裝（research R2）。
- [ ] T023 [P] 在 `tests/unit/test_reward_math.py` 撰寫單元測試：(a) 首步 reward == 0（FR-016）；(b) `lambda_mdd=0, lambda_turnover=0` → reward == log_return（容差 1e-12，SC-007）；(c) drawdown 公式邊界（peak == nav 時 drawdown=0、nav > peak 時亦 0 因 max(0, 負值)=0）；(d) turnover ∈ [0, 1] 不變式；(e) 三項加總 == reward 容差 1e-9（FR-009）。

### Info dict 組裝

- [ ] T024 在 `src/portfolio_env/info.py` 實作 (a) `build_info(env_state) -> dict[str, Any]`：產出 17 個必填 key（data-model.md §6）；(b) `info_to_json_safe(info) -> dict[str, Any]`：`numpy.ndarray` → `list`、`numpy.float*` → `float`、`numpy.int*` → `int`、`numpy.bool_` → `bool`；不丟精度（float64 內）。
- [ ] T025 [P] 在 `tests/unit/test_info_to_json_safe.py` 撰寫單元測試：(a) 含 `numpy.float64`、`numpy.ndarray(float32)`、`numpy.bool_` 之 info 經 `info_to_json_safe` 後 `json.dumps()` 不 raise；(b) round-trip `json.loads(json.dumps(info_to_json_safe(info)))` 對 float64 值差異 == 0（SC-008）；(c) 巢狀 dict（`reward_components`）也被遞迴轉換。

### Render

- [ ] T026 在 `src/portfolio_env/render.py` 實作 `render_ansi(env_state) -> str` 回傳一行文字摘要：`"date={date} nav={nav:.4f} peak={peak:.4f} weights=[{...}] r={reward:+.6f} (log_ret={...}, dd_pen={...}, to_pen={...})"`；`render(env)` 依 `env.render_mode` 分流（None → 回傳 None、"ansi" → 呼叫 `render_ansi`）。
- [ ] T027 [P] 在 `tests/unit/test_render_ansi.py` 撰寫單元測試：(a) `render_mode=None` 時 `env.render()` 回傳 `None`；(b) `render_mode="ansi"` 時回傳 `str` 且含上述格式 token；(c) 對應 reward 三項分量數字正確顯示。

### Info JSON Schema 契約

- [ ] T028 [P] 在 `tests/contract/test_info_schema.py` 撰寫 contract test：使用 `jsonschema.validate` 對 `info_to_json_safe(info)` 之輸出對 `contracts/info-schema.json` 驗證；對 reset 後與多步 step 後皆驗證；故意刪一 key（如 `reward_components`）應 raise `ValidationError`（FR-026、SC-008）。

**Checkpoint**: Foundation 完成 — 配置、loader、observation/action/reward/info/render 模組全部就緒，可進入任一 US 的整合任務。

---

## Phase 3: User Story 1 — 以隨機策略跑通環境（P1）🎯 MVP

**Goal**: 提供可被 `gymnasium.utils.env_checker.check_env` 通過的 `PortfolioEnv`，能跑滿一個 episode、不發生 NaN/inf、reset 兩次 trajectory 一致。

**Independent Test**: 以 `np.random.dirichlet([1]*7)` 為 action 跑 `terminated=True`，驗證 step 數 == `len(_trading_days) - 1`、NAV 序列無 NaN、最終 NAV 為正、reward 累加值在 CI 三平台上 byte-identical。

### Tests for User Story 1（先寫先 fail）⚠️

- [ ] T029 [P] [US1] 在 `tests/contract/test_gym_check_env.py` 撰寫 contract test：對 `PortfolioEnv(config)` 兩種設定（`include_smc=True/False`）皆呼叫 `gymnasium.utils.env_checker.check_env(env)`，預期 0 warning、0 error（SC-003）；亦驗證 `env.metadata == {"render_modes": ["ansi"], "render_fps": 0}`。
- [ ] T030 [P] [US1] 在 `tests/integration/test_random_episode.py` 撰寫 integration test：以 seed=42 reset、Dirichlet 隨機 action 跑到 `terminated=True`；assert (a) step 數 == `env._trading_days.size - 1`、(b) NAV 序列無 NaN/inf、(c) `info["nav"] > 0` 全程、(d) reward 序列無 NaN/inf（US1 acceptance 1）。
- [ ] T031 [P] [US1] 在 `tests/integration/test_cross_platform_trajectory.py` 撰寫 CI 矩陣 test：跑同一 seed=42 + Dirichlet action 序列，將最終 NAV 與每步 reward 序列以 6 位小數寫入 `tests/fixtures/trajectory_seed42.txt`（首次 commit）；後續 CI 三平台跑同 test 比對差異 ≤ 1e-9（FR-020、SC-002）。
- [ ] T032 [P] [US1] 在 `tests/integration/test_init_perf.py` 撰寫效能 test：使用 `time.perf_counter()` 量 `PortfolioEnv(config)` 建構耗時，assert ≤ 10 秒（SC-001 子預算）；fixture 用 002 真實快照（若 `data/raw/` 存在）或退回 mini fixture。
- [ ] T033 [P] [US1] 在 `tests/integration/test_episode_perf.py` 撰寫效能 test：在已建構 env 上量 `reset()` + Dirichlet 跑滿 episode 之耗時，assert ≤ 20 秒（SC-001 子預算）。

### Implementation for User Story 1

- [ ] T034 [US1] 在 `src/portfolio_env/env.py` 實作 `PortfolioEnv(gymnasium.Env)` 主類別骨架：`__init__(self, config)`：(a) 儲存 `self.config`、`self.render_mode = config.render_mode`、設 `self.metadata = {"render_modes": ["ansi"], "render_fps": 0}`；(b) 呼叫 `data_loader.load_environment_data(config)` 取 EnvData，存於 `self._env_data`；(c) 宣告 `self.observation_space = Box(low=-inf, high=inf, shape=(D,), dtype=float32)`（D 由 `include_smc` 決定）、`self.action_space = Box(low=0, high=1, shape=(7,), dtype=float32)`；(d) 初始化 `self.current_index/current_weights/nav_history/peak_nav/_skipped_dates` 為 None（reset 時填）。依賴：T006（config）、T013（loader）、T016（SMC 預計算）。
- [ ] T035 [US1] 在 `src/portfolio_env/env.py` 實作 `reset(self, *, seed=None, options=None) -> tuple[ndarray, dict]`：(a) 呼叫 `seeding.synchronize_seeds(self, seed)`（T011）；(b) 設 `self.current_index = 0`、`self.current_weights = numpy.full(7, 1/7, dtype=float32)`、`self.nav_history = [config.initial_nav]`、`self.peak_nav = config.initial_nav`、`self._skipped_dates = list(self._env_data._skipped_dates_init)`；(c) 組 observation（T018）與 info（含 `is_initial_step=True`、`nan_replaced=0`）；回傳 `(obs, info)`。
- [ ] T036 [US1] 在 `src/portfolio_env/env.py` 實作 `step(self, action) -> tuple[ndarray, float, bool, bool, dict]`：(a) 呼叫 `process_action`（T020）取得 processed action、`action_renormalized`、`position_capped`；(b) 取 `self._env_data._returns[self.current_index + 1]` 與 `_rf_daily[self.current_index + 1]` 計算 `nav_t = nav_{t-1} × (1 + Σ w[i]*ret[i] + w[6]*rf)`（research R2、data-model.md §7 不變式 2）；(c) 更新 `peak_nav = max(peak_nav, nav)`；(d) 推進 `current_index += 1`、`self.current_weights = processed_action`；(e) 呼叫 `compute_reward_components`（T022）算 reward；(f) 組 observation 與 info；(g) `terminated = (self.current_index == self._env_data._trading_days.size - 1)`、`truncated = False`（FR-016/FR-017）。
- [ ] T037 [US1] 在 `src/portfolio_env/env.py` 實作 `render(self) -> str | None`（T026 邏輯）與 `close(self) -> None`（no-op）；確保 `__init__.py` 對外 export `PortfolioEnv` 且 `from portfolio_env import make_default_env` 可用。
- [ ] T038 [US1] 在 `src/portfolio_env/__init__.py` 實作 `make_default_env(data_root, *, include_smc=True) -> PortfolioEnv` 便利建構子（quickstart §2）：等價於 `PortfolioEnv(PortfolioEnvConfig(data_root=Path(data_root), include_smc=include_smc))`。

**Checkpoint**: US1 可獨立驗證 — `pytest tests/contract/test_gym_check_env.py tests/integration/test_random_episode.py tests/integration/test_cross_platform_trajectory.py tests/integration/test_init_perf.py tests/integration/test_episode_perf.py -v` 全綠。

---

## Phase 4: User Story 2 — 驗證 reward 三項成分（P1，與 US1 共為 MVP）

**Goal**: 確保 `info["reward_components"]` 三鍵齊全且加總 == reward；ablation `lambda_mdd=0, lambda_turnover=0` 退化為純 log return。

**Independent Test**: 跑 SC-007 ablation episode 與一般 episode，分別驗證容差 1e-12（純 ablation）與 1e-9（一般）的加總一致性。

### Tests for User Story 2 ⚠️

- [ ] T039 [P] [US2] 在 `tests/integration/test_reward_components.py` 撰寫 integration test：(a) `RewardConfig(lambda_mdd=0, lambda_turnover=0)` 跑全 episode、assert reward[t] == log(nav[t]/nav[t-1])（容差 1e-12，SC-007）；(b) `RewardConfig(lambda_mdd=1.0, lambda_turnover=0.0015)` 跑同 trajectory、assert `info["reward_components"]["log_return"] − drawdown_penalty − turnover_penalty == reward`（容差 1e-9，FR-009、SC-004）；(c) 首步 `info["reward_components"]["log_return"] == 0.0` 且 `info["is_initial_step"] is True`。

### Implementation for User Story 2

- [ ] T040 [US2] 在 `src/portfolio_env/env.py` `step()` 中確認 `info["reward_components"]` 為 dict、含三鍵且型別為 Python `float`（非 numpy scalar，避免 JSON 序列化問題）；首步行為（T035）已透過 `is_initial_step=True` + reward 強制 0 滿足 acceptance；補上 `info["reward_components"]["log_return"]` 在首步亦為 0.0。
- [ ] T041 [US2] 在 `src/portfolio_env/info.py` `build_info` 確保 `reward_components` 鍵順序固定為 `log_return → drawdown_penalty → turnover_penalty`（雖 dict 無語意順序，但便於 JSON Schema 驗證 + log 可讀性）。

**Checkpoint**: US2 可獨立驗證 — `pytest tests/integration/test_reward_components.py -v` 全綠。

---

## Phase 5: User Story 3 — SMC 特徵消融開關（P2）

**Goal**: 在 `include_smc=False` 下 observation 變為 33 維，且 33 維中對應位置與 63 維版本完全相同。

**Independent Test**: 同 seed 下 reset 兩種 config 的環境，比對 first-step observation 之非 SMC 區段 byte-identical。

### Tests for User Story 3 ⚠️

- [ ] T042 [P] [US3] 在 `tests/integration/test_smc_ablation.py` 撰寫 integration test：(a) 兩種 config 下 `env.observation_space.shape` 分別為 (63,) / (33,)；(b) seed=42 reset 後比對 `obs_full[0:24] == obs_price[0:24]`、`obs_full[54:56] == obs_price[24:26]`、`obs_full[56:63] == obs_price[26:33]`（容差 0.0）；(c) 跑 100 步後比對 `info["weights"]` / `info["nav"]` 序列**不**相等（因 observation 不同→ Dirichlet 雖然同 PRNG 但對 obs 不依賴的隨機策略不會差，需額外用 seed 控制 action 與 obs 解耦來驗 — 改為僅驗 first-step obs byte-identical 即可滿足 US3）。

### Implementation for User Story 3

- [ ] T043 [US3] 確認 T018 `build_observation` 與 T034 `__init__` 的 `observation_space.shape` 由 `config.include_smc` 正確切換；若 T018 / T034 已正確實作則此任務僅做 verification + 修補（無新增程式碼）。

**Checkpoint**: US3 可獨立驗證 — `pytest tests/integration/test_smc_ablation.py -v` 全綠。

---

## Phase 6: User Story 4 — Episode 完整 info 紀錄（P2）

**Goal**: 每步 `info` 含 17 個必填 key、首步 NAV == 1.0、JSON 序列化 round-trip 無損。

**Independent Test**: 跑 1000 步 episode，驗證每步 info 通過 JSON Schema 驗證且 `info_to_json_safe` round-trip 無誤差。

### Tests for User Story 4 ⚠️

- [ ] T044 [P] [US4] 在 `tests/integration/test_info_completeness.py` 撰寫 integration test：(a) reset 後 `info["nav"] == 1.0` 且 `info["is_initial_step"] is True`（acceptance 2）；(b) 跑 1000 步、每步 info 通過 `jsonschema.validate(..., info_schema)` 驗證；(c) `info["weights"]` 各步 sum=1（容差 1e-9）、`max(weights[0:6]) <= 0.4`（不變式 3）；(d) `info["data_hashes"]` 每步皆為同一 dict 物件（`id()` 相等）；(e) `info["skipped_dates"]` 為 list 且僅含 ISO date string。

### Implementation for User Story 4

- [ ] T045 [US4] 在 `src/portfolio_env/info.py` `build_info` 中將 `data_hashes` 由 env 物件之 cached attribute（`self._cached_data_hashes`）回傳，確保跨步同 `id()`（避免每步重建 dict 拖效能）。
- [ ] T046 [US4] 在 `src/portfolio_env/env.py` 將 `_cached_data_hashes`（dict）於 `__init__` 結尾組裝一次後 freeze（包成 `types.MappingProxyType`），保證消費者無法 mutate。

**Checkpoint**: US4 可獨立驗證 — `pytest tests/integration/test_info_completeness.py tests/contract/test_info_schema.py -v` 全綠。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 收斂跨 US 之品質檢查、文件、覆蓋率、quickstart 驗證。

- [ ] T047 [P] 在 `tests/integration/test_quickstart_smoke.py` 跑 `quickstart.md` §3、§4、§5、§6、§7 的 code blocks（用 `subprocess` 執行內嵌 Python），assert 預期輸出格式（不檢查具體數字）；對應 quickstart §1 安裝路徑與 §8 pytest 指令亦做 dry-run。
- [ ] T048 [P] 在 `pyproject.toml [tool.pytest.ini_options]` 設 `addopts = "--cov=src/portfolio_env --cov-report=term-missing --cov-fail-under=90"`（憲法 SC-006）；CI 中加 `pytest --cov-report=xml` + Codecov / 等效報告。
- [ ] T049 [P] 在 `docs/` 或 `README.md` 加入 003-ppo-training-env 區段（與 001、002 並列），含一句 feature 描述 + quickstart.md 連結 + 主要 API 範例（直接從 `contracts/api.pyi` 摘要）。
- [ ] T050 在 `src/portfolio_env/env.py`、`config.py`、`reward.py` 等公開模組加 docstring（中文 OK，符合 CLAUDE.md 慣例），引用對應 spec FR / research R 編號便於追溯（憲法 Principle II 解釋性對照）。
- [ ] T051 跑全 quickstart §8 驗證指令 `pytest tests/ -v --cov=src/portfolio_env --cov-report=term-missing` 確認所有測試通過、覆蓋率 ≥ 90%；於 PR 描述附最終 coverage 報告與三平台 CI 連結。
- [ ] T052 [P] 在 `tests/contract/test_public_api.py`（T010）末尾加最終 stub-vs-runtime 一致性 assertion：`__all__` 內每個 symbol 的 `inspect.signature(...)` 與 `contracts/api.pyi` AST 解析結果完全相同；若 stub 須變動，提示開發者同步更新 spec（憲法 Principle V）。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：T001–T005，無上游依賴。T001 完成後 T002–T005 可並行。
- **Foundational（Phase 2）**：T006–T028，依賴 Phase 1 完成。內部依賴：
  - T006 → T007、T008
  - T011 → T012
  - T013 → T014, T015；T013 + smc_features → T016 → T017
  - T018 → T019；T020 → T021；T022 → T023；T024 → T025；T026 → T027
  - T024 + contracts/info-schema.json → T028
  - **BLOCKS Phase 3+ 全部任務**
- **User Stories（Phase 3–6）**：所有 US 共同依賴 Phase 2；US 之間理論上並行，但因共享 `env.py` 主檔，T034–T037 必須序列、T040、T043、T045、T046 在 T034–T037 完成後可並行（不同 method 修補）。
- **Polish（Phase 7）**：T047–T052，依賴所有 US 完成。

### Within Each User Story

- 測試先寫並先 fail（TDD）
- 模組層 (T034–T037) → integration + cross-cutting 修補 (T038, T040–T046)
- US 完成 → checkpoint 跑對應 test 全綠 → 才進下一 US

### Parallel Opportunities

- **Phase 1**：T002, T003, T004, T005 可並行（T001 完成後）。
- **Phase 2**：
  - 所有 `[P]` 標記之 unit test 任務（T007, T012, T015, T017, T019, T021, T023, T025, T027, T028）一旦對應 implementation 任務完成可並行。
  - implementation 任務間：T011/T013/T018/T020/T022/T024/T026 因屬不同檔可在 T006、T008 完成後並行起始。
- **Phase 3 (US1)**：T029–T033 可並行起始（不同檔）；T034–T037 因同 `env.py` 必須序列。
- **跨 US**：US3、US4 之 implementation 修補（T043、T045、T046）可在 US1 主架構（T034–T037）完成後並行。

---

## Parallel Example: User Story 1

```bash
# 先寫測試（T029–T033 全部可並行）：
Task: "Contract test SC-003 in tests/contract/test_gym_check_env.py"
Task: "Random episode integration in tests/integration/test_random_episode.py"
Task: "Cross-platform trajectory in tests/integration/test_cross_platform_trajectory.py"
Task: "Init perf in tests/integration/test_init_perf.py"
Task: "Episode perf in tests/integration/test_episode_perf.py"

# 再實作（T034–T037 同檔需序列）：
Task: "PortfolioEnv __init__ in src/portfolio_env/env.py"
Task: "PortfolioEnv reset in src/portfolio_env/env.py"
Task: "PortfolioEnv step in src/portfolio_env/env.py"
Task: "PortfolioEnv render/close in src/portfolio_env/env.py"
```

---

## Implementation Strategy

### MVP First（US1 + US2，皆為 P1）

1. 完成 Phase 1（T001–T005）。
2. 完成 Phase 2（T006–T028）— foundational 阻塞所有 US。
3. 完成 Phase 3（T029–T038）— US1 隨機 episode + check_env 通過。
4. 完成 Phase 4（T039–T041）— US2 reward 三項驗證。
5. **STOP & VALIDATE**：US1 + US2 同時測試通過即達成 MVP（spec.md 兩個 P1 user story）。
6. 可在此提交一次內部 demo / 論文初稿引用。

### Incremental Delivery

1. MVP 完成 → US3（Phase 5）→ ablation report 可生成。
2. → US4（Phase 6）→ 戰情室前端（feature 007）可開始消費 info dict。
3. → Polish（Phase 7）→ 覆蓋率達標、文件就緒、可交付 review。

### Parallel Team Strategy

- Developer A：Phase 2 config/loader 線（T006, T013, T015, T016, T017）。
- Developer B：Phase 2 observation/action/reward 線（T018–T023）。
- Developer C：Phase 2 info/render/contract 線（T024–T028）+ Phase 1 CI（T004）。
- 三人在 Phase 2 checkpoint 後同步進 US1 + US2（T029–T041，US1 主檔仍由單人主導）。

---

## Notes

- `[P]` = 不同檔、無相互依賴。
- `[US?]` 標記限 Phase 3–6 任務；Phase 1/2/7 任務不掛 US 標籤。
- 每個 US checkpoint 之 pytest 指令全綠才能進下一 US。
- Commit 粒度建議：每完成一個 task（或一組 `[P]` 並行任務）即 commit，commit message 引用 `T0XX` 編號便於追溯。
- 任何 spec / contracts 變動須先回到 `/speckit.specify` 或 `/speckit.plan` 階段（憲法 Principle V），不得在 implement 階段直接改。
- 跨平台驗證（T031）需要 `data/raw/` 真實快照才有意義，建議於 002 implement 完成後再執行；CI 矩陣可暫用 mini fixture pass 然後在 nightly job 跑真資料。
