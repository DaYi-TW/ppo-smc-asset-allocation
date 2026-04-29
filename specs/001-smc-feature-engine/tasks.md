# Tasks: 001-smc-feature-engine

**Input**: Design documents from `/specs/001-smc-feature-engine/`
**Prerequisites**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.pyi](./contracts/api.pyi), [quickstart.md](./quickstart.md)

**Tests**: 包含。spec SC-004 強制覆蓋率 ≥ 90% 且每個特徵須有正反案例；憲法 Principle II
（特徵可解釋性）要求每個特徵附單元測試正反案例 — 故測試任務 MUST 寫入並先失敗（red）
再進入實作（green）。

**Organization**: 任務依 user story（P1 → P4）分組；每個 user story 皆可獨立實作、
獨立測試、獨立交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依）
- **[Story]**：對應 user story（US1/US2/US3/US4）；Setup/Foundational/Polish 不掛標籤
- 每項描述 MUST 包含具體檔案路徑

## Path Conventions

採 Single project layout（plan.md §Project Structure）：
- 原始碼：`src/smc_features/`
- 測試：`tests/{contract,integration,unit}/`
- 套件設定：repo 根 `pyproject.toml`、`requirements-lock.txt`

---

## Phase 1: Setup（共用基礎設施）

**Purpose**：套件骨架、工具鏈、相依鎖定

- [ ] **T001** 建立 src layout 目錄骨架：`src/smc_features/__init__.py`（暫只含 `__version__ = "0.1.0"`）、`src/smc_features/viz/__init__.py`、`tests/contract/`、`tests/integration/`、`tests/unit/`、`tests/__init__.py`、`tests/contract/__init__.py`、`tests/integration/__init__.py`、`tests/unit/__init__.py`、`tests/conftest.py`（先空檔，待 T010 補 fixture）。
- [ ] **T002** 建立 `pyproject.toml`，宣告 build backend（hatchling 或 setuptools）、`[project]` metadata（name `smc-features`、Python 3.11+）、相依範圍：`pandas>=2.0,<3.0`、`numpy>=1.24,<3.0`、`pyarrow>=14,<20`、`mplfinance>=0.12,<0.13`、`plotly>=5.18,<6.0`；optional dev group：`pytest>=8.0`、`pytest-cov>=4.0`、`mypy>=1.10`、`ruff>=0.5`。對應 plan.md §Technical Context。
- [ ] **T003** [P] 產生 `requirements-lock.txt`（research R7）：以 `pip install -e .[dev]` 後 `pip freeze` 鎖定全部精確版本，或改用 `pip-tools` 由 `pyproject.toml` 編譯。提交為 repo root 檔案。
- [ ] **T004** [P] 配置 `pyproject.toml` 中 `[tool.ruff]`（line-length 100、enable rules E/F/W/I/UP/B）、`[tool.mypy]`（strict mode、針對 `smc_features` 套件啟用）、`[tool.pytest.ini_options]`（testpaths = `tests`、addopts `--strict-markers --cov=smc_features --cov-fail-under=90`）。
- [ ] **T005** [P] 建立 `.gitignore` 補充：`.venv/`、`*.egg-info/`、`__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.coverage`、`htmlcov/`、`build/`、`dist/`、`reports/`（quickstart.md §3 視覺化輸出目錄）。若已存在則僅 append。
- [ ] **T006** 建立跨平台 reference fixture 機制：`tests/fixtures/` 目錄、`tests/fixtures/README.md` 說明 fixture 來源（從 002 快照子集抽出）、`tests/fixtures/__init__.py`。實際 parquet fixture 由 T011 寫入。

**Checkpoint**：可執行 `pip install -e .[dev]`、`pytest --collect-only`（無錯誤但 0 測試）、`mypy src/smc_features`（無錯誤）、`ruff check src/`。

---

## Phase 2: Foundational（阻塞所有 user story 的核心型別）

**Purpose**：所有 user story 都消費的不可變資料結構與引擎狀態。**⚠️ CRITICAL**：本階段未完成前，任何 user story 任務都不可開工。

依 data-model.md §3–§6 與 contracts/api.pyi。

- [ ] **T007** 在 `src/smc_features/types.py` 定義 `SMCFeatureParams` frozen dataclass，含 `__post_init__` 驗證（`swing_length >= 1`、`fvg_min_pct >= 0`、`ob_lookback_bars >= 1`、`atr_window >= 1`），違反拋 `ValueError`。對應 data-model.md §3。
- [ ] **T008** [P] 在 `src/smc_features/types.py` 定義 `SwingPoint`、`FVG`、`OrderBlock` 三個 frozen dataclass，欄位完全照 data-model.md §4。同檔可與 T007 平行寫入但不同類別 — 用 [P] 表示邏輯獨立。
- [ ] **T009** [P] 在 `src/smc_features/types.py` 定義 `SMCEngineState`、`FeatureRow`、`BatchResult` frozen dataclass，欄位照 data-model.md §5/§6 與 contracts/api.pyi。`SMCEngineState` 初始狀態工廠函式 `SMCEngineState.initial(params)` 回傳 `bar_count=0`、Optional 欄位 `None`、tuple 欄位 `()`、`trend_state="neutral"`。
- [ ] **T010** 將 `types.py` 公開符號 re-export 至 `src/smc_features/__init__.py`：`SMCFeatureParams`、`SwingPoint`、`FVG`、`OrderBlock`、`SMCEngineState`、`FeatureRow`、`BatchResult`。對齊 contracts/api.pyi `__all__`。
- [ ] **T011** 在 `tests/conftest.py` 建立共用 fixture：`@pytest.fixture default_params`（回傳 `SMCFeatureParams()` 預設值）；`@pytest.fixture sample_ohlcv`（從 `tests/fixtures/nvda_2024H1.parquet` 載入，若 fixture 檔不存在則 skip 並說明如何由 002 快照重建）；`@pytest.fixture deterministic_atol`（回傳 `1e-9`，對應 spec SC-002）。
- [ ] **T012** 撰寫 `tests/contract/test_public_api_signatures.py`：用 `inspect.signature` 比對 `smc_features` 公開函式（`batch_compute`、`incremental_compute`、`visualize`）的參數名、預設值、回傳型別與 `contracts/api.pyi` 完全一致；測試 dataclass frozen 性（嘗試 `obj.x = 1` 應拋 `FrozenInstanceError`）。此測試在 Foundational 階段先 import 失敗（紅燈），於 T020 後轉綠。

**Checkpoint**：types.py 完成；`mypy src/smc_features` 通過；contract 簽章測試已寫好（紅燈）；所有 user story 可平行展開。

---

## Phase 3: User Story 1 - 研究者批次計算 SMC 特徵 (Priority: P1) 🎯 MVP

**Goal**：交付批次計算 API，讓研究者把整段 OHLCV 一次轉成特徵 DataFrame；對應 spec
FR-001~FR-007、FR-016~FR-018、SC-001、SC-002、SC-004。

**Independent Test**：載入 NVDA fixture → 呼叫 `batch_compute(df, params)` → 驗證
回傳 `BatchResult.output` 列數與 fixture 一致、五個特徵欄位齊備、值域合法、第二次
呼叫 byte-identical。

### Tests for User Story 1（先寫先失敗）⚠️

- [ ] **T013** [P] [US1] `tests/unit/test_swing.py`：swing high/low 偵測（research R1）— 正案例（中央 K 棒高於左右 L 根）/ 反案例（鄰近 K 棒含等高，不應確認 swing）/ NaN 列被跳過（FR-015）。對應 SC-004 正反各一。
- [ ] **T014** [P] [US1] `tests/unit/test_bos.py`：BOS 判定 — 正案例（突破前 swing high → `bos_signal=1`）/ 反案例（觸及未破 → `bos_signal=0`）/ 跳空大缺口不誤判（spec Edge Cases）。
- [ ] **T015** [P] [US1] `tests/unit/test_choch.py`：CHoCh 判定 — 正案例（向上趨勢中跌破 last swing low → `choch_signal=-1`）/ 反案例（同向延續 → `choch_signal=0`）/ BOS 與 CHoCh 同時觸發時 CHoCh 優先（FR-019）。
- [ ] **T016** [P] [US1] `tests/unit/test_fvg.py`：FVG 偵測（research R2） — 正案例（bullish FVG: bar i-2.high < bar i.low）/ 反案例（缺口 < `fvg_min_pct`）/ 填補追蹤（後續 K 棒 close 落入區間 → `is_filled=True`）/ 永久未填補 FVG 持續輸出 `fvg_distance_pct`（spec Edge Cases）。
- [ ] **T017** [P] [US1] `tests/unit/test_ob.py`：OB 偵測（research R3） — 正案例（趨勢反轉前最後一根反向 K 棒被標為 OB）/ 反案例（無對應 swing breakout）/ 時間失效（超過 `ob_lookback_bars` 後 `active=False`）/ 結構失效（價格穿越 OB 反向邊界）。
- [ ] **T018** [P] [US1] `tests/unit/test_atr.py`：ATR 計算（research R3，Wilder smoothing） — 正案例（已知 14 根 TR 序列 → 預期 ATR 值，固定到小數第 9 位）/ 邊界（前 13 根輸出 NaN，第 14 根開始有值）/ NaN 列跳過。
- [ ] **T019** [P] [US1] `tests/integration/test_batch_compute.py`：端到端 — `batch_compute(sample_ohlcv, default_params)` 回傳 `BatchResult`、列數保留（FR-001、invariant 1）、index 完全保留（invariant 2）、五個特徵欄位齊備、`bos_signal`/`choch_signal` 值域 ⊂ {-1, 0, 1}、`ob_touched` dtype `bool`、輸出含 `state` 屬性。
- [ ] **T020** [US1] `tests/integration/test_byte_identical.py`：FR-006 / invariant 3 — 連兩次 `batch_compute(df, params)` 結果以 `pd.testing.assert_frame_equal(check_dtype=True, check_exact=True)` 比對；不同 dtype 欄位（int8/float64/bool）皆需精確一致。
- [ ] **T021** [US1] `tests/contract/test_invariants.py`：data-model.md §9 七條不變式 — 1 列數保留 / 2 index 保留 / 3 重現性（兩次呼叫 byte-identical）/ 5 frozen 不可變（嘗試修改 `params` 拋例外）/ 7 CHoCh 優先於 BOS（人造同時觸發 fixture 驗證 `bos_signal==0` 且 `choch_signal!=0`）。Invariant 4（batch/incremental 等價）與 6（NaN 不污染）由 US3、US4 各自覆蓋。

**Tip**：T013–T018 在子模組尚未實作前皆會 `ImportError` — 這就是 red 狀態，預期行為。

### Implementation for User Story 1

- [ ] **T022** [P] [US1] `src/smc_features/swing.py`：實作 `detect_swings(highs: np.ndarray, lows: np.ndarray, swing_length: int, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]`，回傳 `(swing_high_indices, swing_low_indices)`；fractal 規則（research R1）；以 `valid_mask` 跳過品質瑕疵列（FR-015）。docstring MUST 含數學定義（憲法 Principle II）。
- [ ] **T023** [US1] `src/smc_features/structure.py`：實作 `compute_bos_choch(closes, highs, lows, swing_highs, swing_lows, valid_mask) -> tuple[np.ndarray, np.ndarray]`（int8 array），依序檢查每根 K 棒；CHoCh 優先序於同根衝突時生效（FR-019）。docstring 列數學規則。**相依 T022**。
- [ ] **T024** [P] [US1] `src/smc_features/fvg.py`：實作 `FVGTracker` 類別（即使內部使用，仍可 frozen 替換），含 `detect(bars: pd.DataFrame, fvg_min_pct: float) -> list[FVG]` 與 `compute_distances(closes, fvgs) -> np.ndarray`（向量化，回傳 `fvg_distance_pct`）。docstring 含三 K 棒邊界數學（research R2）。
- [ ] **T025** [P] [US1] `src/smc_features/ob.py`：實作 `OBTracker` 含 `detect(bars, swings, ob_lookback_bars) -> list[OrderBlock]`、`compute_touch(bars, obs) -> np.ndarray[bool]`、`compute_distance_ratio(closes, obs, atr) -> np.ndarray`。docstring 含 OB 規則與 ATR 標準化分母（research R3）。
- [ ] **T026** [P] [US1] `src/smc_features/atr.py`：實作 `compute_atr(highs, lows, closes, window: int, valid_mask) -> np.ndarray`，Wilder smoothing；NaN 與 valid_mask=False 列不納入 TR（FR-015）；前 `window-1` 列輸出 NaN。docstring 含公式。
- [ ] **T027** [US1] `src/smc_features/batch.py`：實作 `batch_compute(df, params, *, include_aux=False) -> BatchResult`：(a) 驗證 schema（FR-012/FR-013，缺欄 KeyError、index 非單調 ValueError）；(b) 計算 `valid_mask = (df["quality_flag"] == "ok")` 或全 True；(c) 依序呼叫 swing → ATR → BOS/CHoCh → FVG → OB；(d) 組裝 output DataFrame，dtype 嚴格指定（`bos_signal`/`choch_signal` 用 `pd.Int8Dtype()` nullable、`ob_touched` 用 `pd.BooleanDtype()` nullable、距離欄位用 `float64`）；(e) `include_aux=True` 時加入 6 個 aux 欄位（data-model.md §2）；(f) 構造 `SMCEngineState` 終態並回傳 `BatchResult(output, state)`。**相依 T022–T026**。
- [ ] **T028** [US1] 在 `src/smc_features/__init__.py` re-export `batch_compute` 與 `BatchResult`。對齊 contracts/api.pyi `__all__`。
- [ ] **T029** [US1] 跑 `pytest tests/unit/ tests/integration/test_batch_compute.py tests/integration/test_byte_identical.py tests/contract/test_invariants.py tests/contract/test_public_api_signatures.py -v`，確保 T013–T021 全部由紅轉綠；coverage report 對 `swing.py`/`structure.py`/`fvg.py`/`ob.py`/`atr.py`/`batch.py` 所有檔案 ≥ 90%（spec SC-004）。
- [ ] **T030** [US1] 效能 smoke：以 NVDA 兩年日線 fixture 跑 `batch_compute`，於 `tests/integration/test_performance.py` 加 `@pytest.mark.benchmark`，wall time < 30 秒（spec SC-001）。失敗則 profile 並優化 hot path（向量化、避免 Python loop）。

**Checkpoint**：US1 獨立可運作 — `from smc_features import batch_compute, SMCFeatureParams; batch_compute(df, SMCFeatureParams())` 可用；可作為 MVP 交付。

---

## Phase 4: User Story 2 - 論文審查者視覺化覆核特徵 (Priority: P2)

**Goal**：交付 `visualize()` 雙後端（PNG / HTML），讓不熟悉 SMC 的人 5 分鐘肉眼覆核；對應 spec FR-009~FR-011、SC-005。

**Independent Test**：用 US1 輸出 + `include_aux=True` → `visualize(df, time_range, "out.png", "png")` → 開檔後可清楚見到 K 棒、swing 標記、FVG 帶、OB 帶、BOS/CHoCh 文字標籤。

### Tests for User Story 2 ⚠️

- [ ] **T031** [P] [US2] `tests/integration/test_visualize_png.py`：呼叫 `visualize(..., fmt="png")` 後檔案存在、size > 10 KB、可由 PIL/Pillow 載入解碼成功；`time_range` 越界時拋 `ValueError`（contracts/api.pyi 規範）；缺 aux 欄位時拋 `ValueError`。
- [ ] **T032** [P] [US2] `tests/integration/test_visualize_html.py`：呼叫 `visualize(..., fmt="html")` 後檔案存在；HTML 內含 `plotly` 標籤（驗證 plotly backend 被使用而非 mplfinance）；含 BOS / CHoCh 文字標註。
- [ ] **T033** [P] [US2] `tests/contract/test_visualize_signature.py`：簽章與 contracts/api.pyi 一致（包含 `fmt` 參數命名、`output_path: Path | str` 型別、`params` 為 keyword-only 可選）。

### Implementation for User Story 2

- [ ] **T034** [P] [US2] `src/smc_features/viz/mpl_backend.py`：實作 `render_png(df_with_features, time_range, output_path, params)`：用 mplfinance 的 `addplot` 畫 swing markers / FVG bands（rectangle）/ OB bands；BOS/CHoCh 以 `plt.annotate` 標文字；`params` 不為 None 時於圖底加 footnote（FR-011）。
- [ ] **T035** [P] [US2] `src/smc_features/viz/plotly_backend.py`：實作 `render_html(df_with_features, time_range, output_path, params)`：用 plotly `Candlestick` + `add_shape`（FVG/OB 矩形）+ `add_annotation`（BOS/CHoCh）；輸出為自包含 HTML（`include_plotlyjs="cdn"` 或 `True`，跨平台一致選 `"cdn"` 以縮減檔案）。
- [ ] **T036** [US2] `src/smc_features/viz/__init__.py`：實作 `visualize(df_with_features, time_range, output_path, fmt="png", *, params=None) -> None`：(a) 驗證 time_range 在 index 內；(b) 驗證 aux 欄位齊備（無則 KeyError，提示 `include_aux=True`）；(c) 依 `fmt` dispatch 至兩 backend；(d) 不存在的父目錄拋 `ValueError`。**相依 T034、T035**。
- [ ] **T037** [US2] 在 `src/smc_features/__init__.py` re-export `visualize`。
- [ ] **T038** [US2] 跑 `pytest tests/integration/test_visualize_png.py tests/integration/test_visualize_html.py tests/contract/test_visualize_signature.py -v` 全綠。
- [ ] **T039** [US2] 人工覆核流程文件化：在 `quickstart.md` §3 已存在的「肉眼覆核」段落基礎上，新增 `tests/manual/visual_review_protocol.md`（即使僅一頁），列出受試者操作步驟與預期辨識項目（對應 SC-005 的 80% 識別率測量方法）。

**Checkpoint**：US1 + US2 雙獨立可運作；論文圖可一鍵產出。

---

## Phase 5: User Story 3 - 後端工程師增量計算單根 K 棒 (Priority: P3)

**Goal**：交付 `incremental_compute()` 並保證 batch / incremental byte-identical（spec FR-008、SC-003、invariant 4）。

**Independent Test**：對 N 根 K 棒先 `batch_compute(df)` 取得對照；再 `batch_compute(df.iloc[:-1])` + `incremental_compute(state, df.iloc[-1])` → 比對最後一列每個欄位 byte-identical。

### Tests for User Story 3 ⚠️

- [ ] **T040** [P] [US3] `tests/integration/test_batch_incremental_equivalence.py`：對 fixture 的最後 50 根 K 棒，逐根用 incremental 推進並與 batch 結果逐列比對（int 欄 `==`、float 欄 `math.isclose(atol=1e-9)`、bool 欄 `==`、NaN 位置一致）。覆蓋 invariant 4。
- [ ] **T041** [P] [US3] `tests/integration/test_incremental_latency.py`：跑 1000 次 `incremental_compute` 並用 `time.perf_counter` 量平均延遲；`@pytest.mark.benchmark` 標記，斷言 p50 < 10 ms（spec SC-003）。
- [ ] **T042** [P] [US3] `tests/unit/test_incremental_errors.py`：`new_bar.name` ≤ 前一根 timestamp → `ValueError`；缺欄位 → `KeyError`；params 不可在 incremental 階段被替換（呼叫方僅能透過 state 內嵌的 params）。
- [ ] **T043** [P] [US3] `tests/contract/test_state_immutability.py`：`incremental_compute` 不修改傳入的 `prior_state`（呼叫前後以 `dataclasses.asdict` 比對應相等）；回傳的新 state 為新 instance（`id()` 不同）。

### Implementation for User Story 3

- [ ] **T044** [US3] `src/smc_features/incremental.py`：實作 `incremental_compute(prior_state, new_bar) -> tuple[FeatureRow, SMCEngineState]`：(a) 驗證 timestamp 單調；(b) 驗證 OHLCV 欄位；(c) 從 `prior_state` 取出 swing buffer / FVG 列表 / OB 列表 / ATR buffer；(d) 推進每個子系統並產生 `FeatureRow`；(e) 構造新的 `SMCEngineState`（frozen dataclass.replace）。**相依 T022–T026**。
- [ ] **T045** [US3] **重構不變式**：將 T027 `batch_compute` 內的逐根推進邏輯抽出為共用核心 `_advance_state(state, bar) -> (FeatureRow, new_state)`，讓 `batch_compute` 改用「對每根呼叫 _advance_state 並收集」的形式；如此 batch 與 incremental 共用同一份核心程式碼，自動滿足 invariant 4。**相依 T044**。
- [ ] **T046** [US3] 在 `src/smc_features/__init__.py` re-export `incremental_compute`、`FeatureRow`。
- [ ] **T047** [US3] 跑 T040–T043 + 重跑 T020 / T029 全部測試確保 T045 重構未破壞 US1 結果（regression check）。

**Checkpoint**：US1 + US2 + US3 三者皆獨立可用；後續 PPO 服務化可直接呼叫 incremental。

---

## Phase 6: User Story 4 - 研究者餵入瑕疵資料的容錯處理 (Priority: P4)

**Goal**：對 NaN / volume=0 / 缺日 等品質問題，輸出 NaN 不刪列且不污染下游視窗；對應 spec FR-014、FR-015、SC-006、invariant 6。

**Independent Test**：構造 500 根 K 棒、第 100~104 列 close=NaN 的 fixture → `batch_compute` → 列數仍 500、第 100~104 特徵全 NaN、第 105 起特徵正常、無例外。

### Tests for User Story 4 ⚠️

- [ ] **T048** [P] [US4] `tests/integration/test_quality_flag_propagation.py`：以 002 schema 構造含 `quality_flag in {"missing_close", "zero_volume", "duplicate_dropped"}` 的 DataFrame；驗證對應列特徵全 NaN，其他列正常；驗證下一根有效 K 棒的 swing buffer 並未把瑕疵列納入計算（invariant 6）。
- [ ] **T049** [P] [US4] `tests/unit/test_window_skip.py`：直接測 `swing.detect_swings` 與 `atr.compute_atr` 在 `valid_mask` 含 False 時的行為 — 瑕疵位置產生 NaN、有效視窗仍能形成。
- [ ] **T050** [P] [US4] `tests/unit/test_edge_cases.py`：spec Edge Cases 全部覆蓋 — 資料量不足全 NaN、index 非單調 ValueError、缺欄 KeyError、跨大缺口不誤判 BOS、永久未填補 FVG、incremental 非連續時間 ValueError。

### Implementation for User Story 4

- [ ] **T051** [US4] 補強 `src/smc_features/batch.py`：明確處理 `quality_flag` 欄位 — 缺欄時填 `"ok"`；非 `"ok"` 列加入 `valid_mask=False`；確保 mask 一路傳遞到 swing/ATR/FVG/OB 子模組。**相依 T027**。
- [ ] **T052** [US4] 補強 `src/smc_features/atr.py` 與 `src/smc_features/swing.py`：所有 rolling 視窗輸入皆透過 `valid_mask` 過濾；新增 docstring 段落說明「NaN 列不污染下游視窗」的行為（憲法 Principle II 要求明文）。
- [ ] **T053** [US4] 跑 T048–T050 全綠；重跑全部前面測試（T013–T047）確保未回歸。

**Checkpoint**：四個 user story 全綠；MVP 完整。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**：跨 user story 的最後修整與交付準備。

- [ ] **T054** [P] 對 `src/smc_features/` 全部模組執行 `ruff format` + `ruff check --fix` + `mypy --strict`；最終 0 warning、0 error。
- [ ] **T055** [P] 確認 coverage 整體 ≥ 90%（spec SC-004）：`pytest --cov=smc_features --cov-report=term-missing --cov-report=html`，補測缺漏分支。
- [ ] **T056** [P] 跨平台 reference fixture 測試：CI matrix（Linux / macOS / Windows）跑 `tests/integration/test_cross_platform_fixture.py` — 載入 `tests/fixtures/expected_features.parquet`（先在 Linux 產生並 commit）→ 在當前平台跑 `batch_compute` → 以 `np.allclose(atol=1e-9)` 比對（spec SC-002）。若 fixture 尚未建立，本任務含建立步驟。
- [ ] **T057** [P] `quickstart.md` 端到端驗證：依 quickstart 步驟在乾淨環境執行一次（含 `pip install -r requirements-lock.txt`、batch、visualize、incremental、pytest），全部成功；若有步驟失誤則修 quickstart。對應 spec FR-018。
- [ ] **T058** 重檢 contracts/api.pyi 與 `src/smc_features/__init__.py` 完全對齊（簽章、預設值、`__all__`）；T012 contract 測試保持綠燈。
- [ ] **T059** docstring 終稿：每個特徵函式（`detect_swings` / `compute_bos_choch` / `FVGTracker.detect` / `OBTracker.detect` / `compute_atr`）docstring MUST 含 (a) 判定規則的數學定義或精確自然語言、(b) 至少一個正面 doctest 範例。對應 spec FR-005、憲法 Principle II。
- [ ] **T060** 更新 repo 根 `README.md`（或新增 `src/smc_features/README.md`）：簡介本套件用途、指向 `specs/001-smc-feature-engine/quickstart.md`、列出公開 API。本任務範圍以連結為主，不複製 quickstart 內容。

---

## Dependencies & Execution Order

### Phase 相依

- **Phase 1 (Setup)**：無相依，立即可開始。
- **Phase 2 (Foundational)**：相依 Phase 1；BLOCKS 所有 user story。
- **Phase 3–6 (US1–US4)**：相依 Phase 2 完成。US1 為 MVP，建議優先；US2/US3/US4 在 US1 完成後可由不同人平行展開（彼此獨立檔案）。
- **Phase 7 (Polish)**：相依所有 user story 完成。

### User Story 間相依

- **US1 (P1)**：Foundational 後可獨立；不相依其他 US。MVP。
- **US2 (P2)**：相依 US1 的 `batch_compute(include_aux=True)` 輸出格式 — 但測試可用 stub fixture 提早寫；實作需等 US1 完成。
- **US3 (P3)**：相依 US1 的子模組（swing/structure/fvg/ob/atr）可在 incremental 中重用；T045 重構會修改 US1 的 `batch.py` 內部結構，必須先確保 US1 全綠才動手。
- **US4 (P4)**：相依 US1 的 `batch_compute` 主流程；T051 修改 `batch.py`，需在 US1 全綠後動手；US3 與 US4 對 `batch.py` 的修改互不衝突（T045 動模組組織、T051 動 quality_flag 處理路徑），但建議序執行避免 merge conflict。

### User Story 內部相依

- 測試 MUST 先寫並失敗（red）→ 實作 → 綠（green）。憲法 Principle II 與 spec SC-004 要求。
- types.py 完成後，子模組（swing/structure/fvg/ob/atr）可平行；`batch.py` 等子模組完成後才能組裝。
- `incremental.py`（T044）與 `batch.py` 重構（T045）共用核心 `_advance_state` — 必須一次完成兩個檔案的對齊。

### 平行機會

- **Setup**：T003、T004、T005 [P] 可平行。
- **Foundational**：T008、T009 [P] 可平行（同檔不同類別 — 開發者可兩人合作或單人連寫）。
- **US1 子模組**：T013–T018（單元測試）、T022/T024/T025/T026（實作）皆 [P]，不同檔案無相依。
- **US2 兩 backend**：T034 / T035 [P] 完全獨立。
- **US3 / US4 測試**：T040–T043、T048–T050 各自 [P]。
- **Polish**：T054–T057 [P]。

### 全跑順序建議（單人）

```
T001 → T002 → (T003 ∥ T004 ∥ T005) → T006
  → T007 → (T008 ∥ T009) → T010 → T011 → T012
  → (T013 ∥ T014 ∥ T015 ∥ T016 ∥ T017 ∥ T018 ∥ T019) → T020 → T021
  → (T022 ∥ T024 ∥ T025 ∥ T026) → T023 → T027 → T028 → T029 → T030
  → (T031 ∥ T032 ∥ T033) → (T034 ∥ T035) → T036 → T037 → T038 → T039
  → (T040 ∥ T041 ∥ T042 ∥ T043) → T044 → T045 → T046 → T047
  → (T048 ∥ T049 ∥ T050) → T051 → T052 → T053
  → (T054 ∥ T055 ∥ T056 ∥ T057) → T058 → T059 → T060
```

---

## Implementation Strategy

### MVP 路徑（最小可交付）

1. **Phase 1 + Phase 2** → 套件骨架與型別就緒。
2. **Phase 3 (US1)** → 批次計算可用，研究者已能產出特徵 DataFrame。
3. **STOP & VALIDATE**：跑 quickstart §2，肉眼確認 NVDA 一段資料的特徵分布合理（手動 sanity check）。
4. **可作為 MVP 提交 PR、合併進 main、給後續 PPO feature 消費**。

### Incremental 交付

1. MVP（US1）→ 第二輪加 US2（視覺化）→ 第三輪加 US3（增量）→ 第四輪加 US4（容錯強化）→ Polish。
2. 每輪結束 commit + tag（建議 `v0.1.0-us1` / `v0.2.0-us2` ...），便於回溯。

### 多人平行

- 開發者 A：US1（主 MVP）— 涵蓋 swing/structure/fvg/ob/atr/batch。
- 開發者 B：US2（視覺化）— 完全獨立檔案，US1 的 fixture 一就緒即可開工。
- 開發者 C：US3（增量）+ US4（容錯）— 兩者皆需動 `batch.py`，由同人序執行避免衝突。

---

## Notes

- `[P]` = 不同檔案、無相依，可平行。
- `[Story]` = US1/US2/US3/US4，對應 spec.md 的 user story 編號。
- 紅 → 綠 順序：每個 user story 內測試先寫並失敗，再寫實作。
- 每個任務完成後 commit；建議 commit message 前綴 `[001-T0XX]`。
- 任何 checkpoint 處可暫停並驗證 user story 獨立性。
- 避免：模糊任務、同檔衝突、跨 story 偶合導致無法獨立測試。
- 五大原則合規由 plan.md §Constitution Check 涵蓋；本檔不重複，但 task 內容（測試正反案例、docstring 數學、frozen dataclass、cross-platform fixture）已逐一映射到該 gate。
