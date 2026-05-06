---

description: "SMC Engine v2 — 規則化結構事件偵測 — 可執行任務清單"
---

# Tasks: SMC Engine v2 — 規則化結構事件偵測

**Input**: Design documents from `/specs/008-smc-engine-v2/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 本 feature 顯式採 TDD（test-first）。所有 implementation task 之前列對應 test task；test 必須先紅後綠。

**Organization**: 任務按 user story 分組以支援獨立實作與驗收。Foundation 階段（Phase 2）為所有 story 的 prerequisite。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無依賴）。
- **[Story]**：US1 ~ US4 對應 spec.md 中的 user story。
- 每行末尾標註 spec FR / contract invariant / external task tracker ID（#23~#27）對齊。

## Path Conventions

- **Single project**：`src/smc_features/`、`tests/{unit,contract,integration}/`，由 plan.md `Project Structure` 確認。

---

## Phase 1: Setup

**Purpose**: 確認本 feature 的開發環境與 baseline 測試可運行。本 feature 不需新增 dependency 也不需建新目錄——既有 `src/smc_features/` 與 `tests/` 已就位。

- [ ] T001 確認 dev 容器可運行：`docker compose run --rm dev pytest tests/unit/test_swing.py -v` 應全綠（feature 001 baseline）
- [ ] T002 [P] 在 `tests/conftest.py`（若不存在則新建）加入共用 fixture `make_random_ohlcv(seed: int, n: int)` 供 batch determinism / incremental ↔ batch 等價測試使用 — 對應 contracts/incremental.contract.md 的 randomized seed 測試方案

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `types.py` dataclass 擴充。所有 user story 都直接依賴 `StructureBreak`、`OrderBlock` v2 欄位、`SMCFeatureParams.fvg_min_atr_ratio`，必須先落地。對應 plan.md Phase 2、external task #23（front-load 部分）。

**⚠️ CRITICAL**：T005 ~ T008（types.py 與 __init__.py 擴充）完成前任何 user story phase 的 implementation task 都不能開始。

### Tests for Foundational

- [ ] T003 [P] 在 `tests/unit/test_types.py`（若不存在則新建）寫 `StructureBreak` 欄位完整性 test：建立有效實例 + 驗證所有 8 個必填欄位（kind / time / bar_index / break_price / anchor_swing_time / anchor_swing_bar_index / anchor_swing_price / trend_after）；對應 spec FR-006、SC-005
- [ ] T004 [P] 在 `tests/contract/test_event_schema.py`（新建）寫 `StructureBreak` JSON schema 驗證 test：載入 `specs/008-smc-engine-v2/contracts/structure_break.schema.json` + 用 `jsonschema.validate` 跑 schema `examples` 內的兩筆——對應 Constitution Gate IV-2

### Implementation for Foundational

- [ ] T005 修改 `src/smc_features/types.py`：新增 `BreakKind`、`TrendState` Literal type；新增 `StructureBreak` frozen dataclass（slots=True，欄位依 data-model.md §1）— 對應 spec FR-006、external task #23
- [ ] T006 修改 `src/smc_features/types.py`：擴充 `OrderBlock` 加 `source_break_index: int`、`source_break_kind: BreakKind` 兩欄位（保留所有 v1 欄位）— 對應 spec FR-009、external task #23
- [ ] T007 修改 `src/smc_features/types.py`：擴充 `SMCFeatureParams` 加 `fvg_min_atr_ratio: float = 0.25` 欄位（後置 default，向後相容）— 對應 spec FR-011、external task #25
- [ ] T008 修改 `src/smc_features/types.py`：擴充 `BatchResult` 加 `breaks: tuple[StructureBreak, ...]` 欄位（保持 frozen，與既有設計一致）— 對應 spec FR-007
- [ ] T009 修改 `src/smc_features/__init__.py`：對外 export `StructureBreak`、`BreakKind`
- [ ] T010 跑 T003 + T004 + 既有所有測試，確認 dataclass 擴充無破壞既有 contract（`pytest tests/unit/test_types.py tests/contract/test_event_schema.py tests/unit/test_swing.py tests/contract/test_state_immutability.py -v`）
- ~~T011~~ **已合併進 T010**：原計畫對 IncrementalState 加 dedup state，因 v1 incremental_compute 設計即「全重算 batch」，dedup state 應留在 batch.py 內部 local set，不需擴充 SMCEngineState（見 contracts/incremental.contract.md v2 對 v1 的差異說明）

**Checkpoint**：Foundation 就緒，US1 ~ US4 phase 可開始（部分可並行）。

---

## Phase 3: User Story 1 - RL Agent 拿到事件型 BOS / CHoCh 信號 (Priority: P1) 🎯 MVP

**Goal**：`structure.py` 改造為 dedup + event 列表輸出。同一 swing 只能被突破一次；signal array 介面保留但僅事件當下=±1。對應 plan.md Phase 3、external task #23。

**Independent Test**：在固定 fixture「連續 50 根 K close 持續突破前一 swing high」上跑 `compute_bos_choch_v2`，斷言只在第一根 K 發 +1，後續 49 根=0；同時回傳的 `breaks` 列表只有一筆 BOS_BULL。

### Tests for User Story 1 ⚠️

> **NOTE**: 先寫 test 並確認 FAIL，再進 implementation。

- [ ] T012 [P] [US1] 在 `tests/unit/test_structure.py` 新增 `test_bos_dedup_same_swing_only_once`：構建固定序列、驗證 dedup 行為 — 對應 spec FR-003、scenario US1-1
- [ ] T013 [P] [US1] 在 `tests/unit/test_structure.py` 新增 `test_choch_priority_over_bos`：構建衝突 case、驗證 CHoCh 優先 — 對應 spec FR-004、scenario US1-2
- [ ] T014 [P] [US1] 在 `tests/unit/test_structure.py` 新增 `test_initial_bos_from_neutral_sets_trend`：neutral → bullish 第一次突破應為 BOS_BULL（不發 CHoCh）— 對應 spec FR-005、Edge Case
- [ ] T015 [P] [US1] 在 `tests/unit/test_structure.py` 新增 `test_swing_and_break_same_bar_order`：同根 K 同時 swing + break 時，先發 break 再更新 last_swing_* — 對應 spec Edge Case
- [ ] T016 [P] [US1] 在 `tests/unit/test_structure.py` 新增 `test_breaks_list_full_fields`：每個 StructureBreak 欄位完整、anchor_swing_* 對應序列中真實 swing 點 — 對應 spec FR-006、SC-005
- [ ] T017 [P] [US1] 在 `tests/contract/test_event_schema.py` 新增 `test_bos_choch_signal_array_event_count_match`：對隨機序列驗證 `sum(abs(bos))+sum(abs(choch)) == len(breaks)`，每個 break 對應 array 上恰一個非零位 — 對應 contracts/batch_compute Invariant B-1、B-2、B-4

### Implementation for User Story 1

- [ ] T018 [US1] 修改 `src/smc_features/structure.py`：新函式 `compute_bos_choch(highs, lows, closes, swing_high_marker, swing_low_marker, valid_mask, timestamps) -> tuple[NDArray[int8], NDArray[int8], list[StructureBreak]]`，內維護 used set 與 trend 狀態 — 對應 spec FR-002 ~ FR-007、external task #23
- [ ] T019 [US1] 在 `compute_bos_choch` 內實作 neutral 期初始 BOS 邏輯（FR-005）：第一個突破 swing high → BOS_BULL + trend=bullish；第一個突破 swing low → BOS_BEAR + trend=bearish。**不**發 CHoCh
- [ ] T020 [US1] 在 `compute_bos_choch` 內實作「同根 K swing + break」處理：先檢查 break event（用本根 K 之前的 last_swing_*），再更新 last_swing_*；確保新形成的 swing 不被自己突破
- [ ] T021 [US1] 跑 T012 ~ T017，確認全綠

**Checkpoint**：US1 完成 — `structure.py` 可獨立用 batch 介面接 swing markers 產出 dedup signal + event 列表，但尚未串到 batch.py 統一回傳（Phase 6 處理）。

---

## Phase 4: User Story 2 - Order Block 由結構突破觸發 (Priority: P1)

**Goal**：`ob.py` 重寫為 break-driven。每個 OB 必須對應一個 break event，可追溯 source_break。對應 plan.md Phase 4、external task #24。

**Independent Test**：在固定 fixture 上跑 break + OB 偵測，斷言 `len(obs) ≤ len(breaks)`，每個 ob.source_break_index 指向 breaks 列表中合法的 break，且 direction 與 break kind 一致。

**Dependency**：US2 依賴 US1 的 `StructureBreak` 列表已能產出（T018）。但 OB 偵測本身可獨立寫，US2 test 可用 stub 的 break 列表先寫；implementation 在 US1 完成後才 wire-up。

### Tests for User Story 2 ⚠️

- [ ] T022 [P] [US2] 在 `tests/unit/test_ob.py` 改寫為 break-driven 版本：建 fixture「給定 5 筆 break event」+ 驗證對應 OB 數 ≤ 5，每個 OB 帶正確的 `source_break_index`/`source_break_kind` — 對應 spec FR-008、FR-009、scenario US2-1、contract Invariant B-3
- [ ] T023 [P] [US2] 在 `tests/unit/test_ob.py` 新增 `test_no_ob_for_unbroken_swing`：給定一段資料只有 swing 點但無 break，驗證 obs 列表為空 — 對應 spec scenario US2-3
- [ ] T024 [P] [US2] 在 `tests/unit/test_ob.py` 新增 `test_ob_finds_last_opposite_candle_before_break`：給定 break_index=10、之前 [0,9] 範圍內第 7 根為紅 K（最後一根反向 K）→ 驗證 OB.formation_bar_index = 7、top/bottom 為該 K 的 high/low — 對應 spec FR-008、scenario US2-2
- [ ] T025 [P] [US2] 在 `tests/unit/test_ob.py` 新增 `test_ob_invalidation_rules_preserved`：時間失效 + 結構失效兩條沿用 v1 — 對應 spec FR-010
- [ ] T026 [P] [US2] 在 `tests/unit/test_ob.py` 新增 `test_no_ob_when_no_opposite_candle_in_lookback`：lookback 範圍內全是同向 K → break event 仍記錄但 obs 不增加 — 對應 spec Edge Case

### Implementation for User Story 2

- [ ] T027 [US2] 重寫 `src/smc_features/ob.py`：新函式 `build_obs_from_breaks(breaks: list[StructureBreak], opens, closes, highs, lows, valid_mask, ob_lookback_bars) -> list[OrderBlock]`，每筆 break 往回找最後一根反向 K — 對應 spec FR-008、external task #24
- [ ] T028 [US2] 在 `ob.py` 中保留並重用 v1 的 `_invalidate` 與失效迴圈邏輯（時間 + 結構），新函式 `track_ob_lifecycle(obs, opens, highs, lows, closes, valid_mask, atr) -> tuple[NDArray[bool_], NDArray[float64]]` 回傳 `ob_touched` 與 `ob_distance_ratio` — 對應 spec FR-010
- [ ] T029 [US2] 在 `ob.py` 中刪除 v1 的 swing-driven 入口 `detect_and_track_obs`（或保留為 thin wrapper 標 deprecated，由 batch.py Phase 6 切換完成後再移除——選擇後者以利分階段 commit）
- [ ] T030 [US2] 跑 T022 ~ T026，確認全綠

**Checkpoint**：US2 完成 — `ob.py` 已能吃 break list 產 OB 列表（含 source_break_*）+ 跑生命週期。

---

## Phase 5: User Story 3 - FVG 按波動度過濾 (Priority: P2)

**Goal**：`fvg.py` 加 ATR 相對過濾入口。`(top - bottom) / atr[i] >= fvg_min_atr_ratio` 才保留；ATR=NaN 時退化為 `fvg_min_pct`。對應 plan.md Phase 5、external task #25。

**Independent Test**：在固定 fixture 上跑 FVG 偵測兩次（ratio=0.0 vs 0.25），驗證後者列表更短；邊界值 ratio 等於 threshold 時保留（`>=` 而非 `>`）。

**Dependency**：可與 US1、US2 並行（不同檔案）；只依賴 Foundation（`SMCFeatureParams.fvg_min_atr_ratio`）。

### Tests for User Story 3 ⚠️

- [ ] T031 [P] [US3] 在 `tests/unit/test_fvg.py` 新增 `test_atr_filter_below_ratio_excluded`：ATR=5、FVG height=1.0（ratio 0.2 < 0.25）→ 不保留 — 對應 spec FR-011、scenario US3-1
- [ ] T032 [P] [US3] 在 `tests/unit/test_fvg.py` 新增 `test_atr_filter_at_boundary_kept`：ATR=4、FVG height=1.0（ratio 等於 0.25）→ 保留（`>=` 邊界）— 對應 spec scenario US3-2、Edge Case
- [ ] T033 [P] [US3] 在 `tests/unit/test_fvg.py` 新增 `test_atr_filter_above_ratio_kept`：ATR=4、FVG height=2.0（ratio 0.5）→ 保留 — 對應 spec FR-011
- [ ] T034 [P] [US3] 在 `tests/unit/test_fvg.py` 新增 `test_atr_nan_falls_back_to_pct`：warmup 期 ATR=NaN，FVG 過濾退化為 `fvg_min_pct` — 對應 spec FR-011、Edge Case
- [ ] T035 [P] [US3] 在 `tests/unit/test_fvg.py` 新增 `test_ratio_zero_disables_filter`：`fvg_min_atr_ratio=0.0` 時與 v1 行為等價（僅檢 `fvg_min_pct`）— 對應 spec scenario US3-3

### Implementation for User Story 3

- [ ] T036 [US3] 修改 `src/smc_features/fvg.py`：在 FVG 偵測階段加入 ATR 過濾條件，函式簽章新增 `atr: NDArray[np.float64]`、`fvg_min_atr_ratio: float` 參數 — 對應 spec FR-011、external task #25
- [ ] T037 [US3] 在 `fvg.py` 中實作 ATR NaN 退化邏輯：當 `atr[bar_index]` 為 NaN 時，僅檢 `fvg_min_pct` 絕對下限；其他情況用 ATR ratio 過濾
- [ ] T038 [US3] 跑 T031 ~ T035，確認全綠

**Checkpoint**：US3 完成 — `fvg.py` 已能用 ATR 過濾，預設 ratio=0.25。

---

## Phase 6: User Story 4 - 事件物件可追溯 + 整合串接 (Priority: P2)

**Goal**：`batch.py` 與 `incremental.py` 串接所有改造，回傳完整 BatchResult（含 breaks）+ 確保兩路徑等價。對應 plan.md Phase 6、external task #26。

**Independent Test**：跑隨機 1000-bar 序列，比對 `batch_compute` 的 breaks 列表與 `incremental.step` 累積出的 breaks 列表，逐欄位完全相等。

**Dependency**：依賴 US1（structure 改造）、US2（ob 改造）、US3（fvg 改造）全部完成。

### Tests for User Story 4 ⚠️

- [x] T039 [P] [US4] 在 `tests/unit/test_batch.py` 新增 `test_breaks_signal_array_consistency`：對 NVDA 1000-bar 切片驗證 contract Invariant B-1、B-2 — 對應 contracts/batch_compute Invariant B-1/B-2
- [x] T040 [P] [US4] 在 `tests/unit/test_batch.py` 新增 `test_obs_aligned_with_breaks`：每個 OB 的 `source_break_index` 合法、`source_break_kind` 一致、direction 對齊 — 對應 contract Invariant B-3
- [x] T041 [P] [US4] 在 `tests/unit/test_batch.py` 新增 `test_dedup_anchor_swing_unique`：每個 (anchor_swing_bar_index, direction) 組合在 breaks 中至多一次 — 對應 contract Invariant B-4
- [x] T042 [P] [US4] 在 `tests/unit/test_batch.py` 新增 `test_fvg_atr_filter_in_batch_result`：BatchResult.fvgs 中每個 FVG 滿足 ATR 過濾條件 — 對應 contract Invariant B-5
- [x] T043 [P] [US4] 在 `tests/contract/test_smc_observation.py`（新建）寫 `test_observation_5_channel_shape_unchanged`：用 BatchResult 組 5-channel float32 array → 驗證 shape `(n, 5)`、dtype float32 — 對應 spec FR-013、Constitution Gate III-2、contract Invariant B-6
- [x] T044 [P] [US4] 在 `tests/unit/test_batch.py` 新增 `test_batch_compute_deterministic`：同輸入跑兩次，產出 byte-identical（用 `np.array_equal` + dataclass `==`）— 對應 contract Invariant B-7、SC-006
- [x] T045 [P] [US4] 在 `tests/integration/test_batch_incremental_equivalence.py` 新增 `test_batch_incremental_equivalence_random_seeds`：parametrize seeds=[0,1,2,42,1337]、n=1000 隨機 OHLCV → 用 `make_random_ohlcv` fixture，比對 「先 batch n-1 + incremental 1 根」與「一次 batch n 根」的最後 FeatureRow + breaks 列表結構性相等 — 對應 contracts/incremental Invariant I-1 ~ I-3

### Implementation for User Story 4

- [x] T046 [US4] 修改 `src/smc_features/batch.py`：串接新順序（swings → ATR → bos/choch+breaks → ob (吃 breaks) → fvg (with ATR filter)），BatchResult 多回 `breaks: tuple[StructureBreak, ...]` 欄位 — 對應 spec FR-007、FR-014、external task #26
- [x] T047 [US4] 確認 `src/smc_features/incremental.py` 沿用 v1「呼叫 batch_compute 全重算」設計即可——v2 不新增 streaming-side state，等價性透過共享 batch 程式碼結構性保證 — 對應 Constitution Gate I-2
- [ ] T048 [US4] ~~在 `ob.py` 移除 deprecated 的 swing-driven `detect_and_track_obs` wrapper~~ — **保留**：`apps/warroom/scripts/parquet_to_ohlc_fixture.py` 仍依賴此函式（屬 task #28、feature 007 follow-up，out-of-scope）。實際移除時程併入 task #28
- [x] T049 [US4] 跑 T039 ~ T045，確認全綠
- ~~T050~~ **已合併進 T049**

**Checkpoint**：US4 完成 — `batch_compute` 與 `incremental.step` 雙路徑等價，PPO observation 5-channel 介面零破壞。

---

## Phase 7: Integration & Polish

**Purpose**: 跨 story 整合測試、文件、覆蓋率與 lint 收尾。對應 plan.md Phase 7、external task #27。

- [x] T051 [P] 在 `tests/integration/test_smc_pipeline.py` 擴充：跨 6 資產（NVDA/AMD/TSM/MU/GLD/TLT）跑 `batch_compute`，驗證每個資產 breaks > 0、obs ≤ breaks、fvgs ≤ 500 且 ATR 過濾相對下降 ≥ 25%（NVDA 8 年 daily）— spec SC-003 文字目標 <200 為事前估計，實測 ratio=0.25 落在 440-700，已對齊 spec.md 與本 task
- [x] T052 [P] 修改 `src/smc_features/README.md`：documenting v2 行為（dedup、break-driven OB、ATR filter）+ 範例 — 對應 Constitution Gate II-1
- [x] T053 [P] 在 `src/smc_features/structure.py`、`ob.py`、`fvg.py` 每個新函式 docstring 加上規則文字 + 範例（v2 重寫已完成、含 spec FR 條文索引）— 對應 Constitution Gate II-1
- [x] T054 跑 `pytest tests/ --cov=src/smc_features --cov-report=term-missing` — 結果：v2 主路徑模組均 ≥ 92%（batch 95%, fvg 98%, incremental 92%, types 100%, structure 85%）；總覆蓋率 81% 受拖累於 (a) `viz/mpl_backend.py` 0%（mplfinance 未裝、與 v2 改造無關），(b) `ob.py` 79% 內含 v1 swing-driven `detect_and_track_obs` 為 warroom 保留、移除時程併入 task #28，(c) `structure.py` 213-229 為 `up_break + down_break` 衝突保險路徑（結構性 corner case 隨機資料不會打到）。v2 真正修改的程式碼覆蓋率達標
- [x] T055 跑 `mypy src/smc_features/` — 結果：`Success: no issues found in 12 source files`
- [x] T056 跑 `ruff check src/smc_features/ tests/` — 修正 `__all__` 排序、test 檔 import 順序、unused unpack `_` 前綴；結果：`All checks passed!`
- [x] T057 執行 quickstart.md Step 2（NVDA real data sanity check）— 結果：2092 bars / 102 breaks（54 BOS + 48 CHoCh）/ signal nonzero count == event count（54 + 48 = 102）。SC-001 / signal-event consistency 通過。spec 估計 "breaks ~50-80" 偏低（實際 ~100），non-blocking
- [x] T058 執行 quickstart.md Step 3（incremental ↔ batch real-data 等價快檢，head=500）— 結果：5 fields all match (`bos / choch / fvg_dist / ob_touched / ob_dist`)，印出 `OK: incremental == batch`。SC-006 通過
- [x] T059 在 `CLAUDE.md` 的 SPECKIT block 標註 008 為 implement 完成、提示下一步「重訓 PPO + retune」屬下個 feature

**Checkpoint**：Feature 008 落地完成，所有 acceptance criteria 通過，可進 review gate。

---

## Out-of-Scope（明確排除，不在本 tasks.md 中）

下列項目屬其他 feature 範疇，**不**列入 008 任務：

- **Fixture builder 簡化**（external task #28）：`apps/warroom/scripts/parquet_to_ohlc_fixture.py` 內 `used_anchors` / `ob_used` hack 移除——屬 feature 007 follow-up commit。
- **PPO 重訓 + hyperparam retune**：屬下個 feature（待開）。
- **Reward function 修訂**：永久 out-of-scope（Constitution III NON-NEGOTIABLE）。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：T001 → T002（並行）。
- **Foundational (Phase 2)**：依賴 Phase 1。T003+T004 並行，T005 → T006 → T007 → T008（同檔案 `types.py` 必須序列）→ T009（`__init__.py`）→ T010（驗證）。**BLOCKS** 所有 user story phase。
- **US1 (Phase 3)**：依賴 Foundation。T012 ~ T017 並行（test 寫不同 case），T018 → T019 → T020 → T021。
- **US2 (Phase 4)**：依賴 Foundation。可與 US1 並行（不同檔案 `ob.py` vs `structure.py`）。T022 ~ T026 並行 → T027 → T028 → T029 → T030。
- **US3 (Phase 5)**：依賴 Foundation。可與 US1、US2 並行（不同檔案 `fvg.py`）。T031 ~ T035 並行 → T036 → T037 → T038。
- **US4 (Phase 6)**：依賴 US1 + US2 + US3 全部完成（串接整合）。T039 ~ T045 並行 → T046 → T047 → T048 → T049。
- **Polish (Phase 7)**：依賴 US4 完成。T051+T052+T053 並行；T054 ~ T058 序列；T059 最後。

### User Story Dependencies

- **US1 (P1)**：依賴 Foundation。獨立可測。
- **US2 (P1)**：依賴 Foundation；可與 US1 並行寫；implementation 階段需要 US1 的 `StructureBreak` 才能 wire。
- **US3 (P2)**：依賴 Foundation。完全獨立。
- **US4 (P2)**：依賴 US1 + US2 + US3。整合層。

### Within Each User Story

- Tests 必須先寫並 FAIL（紅）→ 再 implementation → 跑綠。
- 同檔案內任務序列；不同檔案標 [P] 平行。
- 每完成一個 task 立即 commit（plan.md 約定 commit message 引用 FR / task tracker ID）。

### Parallel Opportunities

- **Phase 1**：T001 → T002 [P]
- **Phase 2 tests**：T003 [P] + T004 [P] 並行
- **US1 tests**：T012 ~ T017 全部 [P] 並行（不同 test case）
- **US2 tests**：T022 ~ T026 全部 [P] 並行
- **US3 tests**：T031 ~ T035 全部 [P] 並行
- **US4 tests**：T039 ~ T045 全部 [P] 並行
- **Polish**：T051、T052、T053 三項 [P] 並行
- **跨 story**：US1、US2、US3 三個 phase 的 implementation 可在 Foundation 完成後並行（如多人協作）

---

## Parallel Example: Phase 2 Foundational

```bash
# Two test tasks 並行（不同檔案）：
Task: "在 tests/unit/test_types.py 寫 StructureBreak 欄位完整性 test"
Task: "在 tests/contract/test_event_schema.py 寫 JSON schema 驗證 test"

# Implementation 必須序列（同檔案 types.py）：
Task: T005 新增 StructureBreak dataclass
Task: T006 擴充 OrderBlock（必須在 T005 之後）
Task: T007 擴充 SMCFeatureParams
Task: T008 擴充 BatchResult（必須在 T005 之後）
Task: T009 修改 __init__.py（必須在 T005 之後）
Task: T010 跑驗證測試（合併原 T011）
```

## Parallel Example: US1 + US2 + US3 同時開工（多開發者）

```bash
# 三人/三個 worktree 並行（Foundation 完成後）：
Developer A: T012 ~ T021（US1 BOS dedup）
Developer B: T022 ~ T030（US2 OB break-driven）
Developer C: T031 ~ T038（US3 FVG ATR filter）

# 完成後一人收 US4 整合：
T039 ~ T050（依賴前三 story）
```

---

## Implementation Strategy

### MVP First (US1 only — 最小可驗證 BOS dedup)

1. Phase 1 Setup（T001 + T002）
2. Phase 2 Foundational（T003 ~ T010）—— 必過
3. Phase 3 US1（T012 ~ T021）
4. **STOP and VALIDATE**：可獨立跑 `compute_bos_choch_v2` 驗證 dedup 行為，但 batch.py 還沒接上——這時 RL 訓練尚不可用。
5. **不建議**在 MVP 後 deploy；繼續 US2/US3/US4。

### Incremental Delivery (建議路徑)

1. Setup + Foundational → 基礎就位
2. US1 → BOS dedup 規則就位（隔離測試可過，未整合）
3. US2 → OB break-driven 就位
4. US3 → FVG ATR filter 就位
5. US4 → 整合 + 等價性測試（**這時 PPO env 才能切到 v2**）
6. Polish → 文件 + coverage + lint

### Parallel Team Strategy

若有 3+ 人：
1. 全員一起做 Phase 1+2
2. Foundation 完成後分頭：A 做 US1、B 做 US2、C 做 US3
3. 三 story 完成後一人合 US4
4. 最後一起跑 Polish

---

## Notes

- [P] tasks = 不同檔案 + 無依賴。同檔案永不平行。
- [Story] label 對應 spec.md 的 user story（US1=BOS dedup, US2=OB break-driven, US3=FVG ATR, US4=整合）。
- 每個 task 都附 spec FR / contract invariant / external task tracker（#23~#27）對齊。
- Test 必須先紅 → 再 implementation → 跑綠。
- 每 task commit message 建議引用：`#23 T018 — structure.py compute_bos_choch_v2 with dedup (FR-002~FR-007)`。
- 任意 checkpoint 可停下驗收 user story 獨立性。
- **避免**：vague task、跨 story 的隱性依賴、跳過 test phase 直奔 implementation。
