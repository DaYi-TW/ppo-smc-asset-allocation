# Tasks: PPO Live Tracking Dashboard

**Input**: Design documents from `specs/010-live-tracking-dashboard/`
**Prerequisites**: spec.md (27 FR / 9 SC) ✓, plan.md (Phases 0–7) ✓, research.md (R1–R12) ✓, data-model.md (5 entities + 6 invariants) ✓, contracts/openapi-live-tracking.yaml ✓, quickstart.md ✓

**Convention**:
- 每個 task 目標 ≤ 30 分鐘、可獨立 commit
- `[P]` = 不同檔案、無相依，可並行
- Test-first：每個 implementation 之前先列 RED test
- 每個 task 標出 `(FR-xxx)` 對齊 spec.md
- Constitution gate tests 在最後 Phase 7 鎖

---

## Phase 1: Setup

- [ ] T001 Add `pandas_market_calendars>=4.4` to `pyproject.toml` deps + `requirements-lock.txt` 重新 pip-compile (FR-007)
- [ ] T002 Create empty package `src/live_tracking/__init__.py` (exposes `__version__ = "0.1.0"`) (FR-001)
- [ ] T003 [P] Add env keys to `src/inference_service/config.py`: `LIVE_ARTEFACT_DIR`, `LIVE_START_DATE=2026-04-29`, `LIVE_INITIAL_NAV=1.7291986`, `LIVE_POLICY_RUN_ID` (FR-002)
- [ ] T004 [P] Update `infra/docker-compose.gateway.yml` and `infra/docker-compose.inference.yml`: 005 service 加 `volumes: ["./runs:/app/runs"]` (FR-001 持久化)

---

## Phase 2: Foundational — Calendar + Status state machine + Store skeleton

> 對應 plan Phase 1 (data-model: LiveTrackingStatus, LiveTrackingArtefact 部分骨架)

### Tests first (RED)

- [ ] T005 [P] Write `tests/unit/live_tracking/test_calendar.py`：covers (a) empty range when last_date == today, (b) skip weekend, (c) skip Federal holidays (Memorial Day 2026-05-25), (d) handle half-day market (Black Friday 2026-11-27 仍視為交易日), (e) 起始日 today < 2026-04-29 → return [] (FR-007 edge case)
- [ ] T006 [P] Write `tests/unit/live_tracking/test_status.py`：covers (a) default load when file absent → all None, (b) round-trip write → load byte-equal, (c) `mark_running(pid, started_at)` 設 is_running=True 且 running_pid 非空, (d) `mark_succeeded(last_frame_date)` 清 last_error + 更新 last_updated, (e) `mark_failed("DATA_FETCH: ...")` 保留 last_frame_date 不變 + 寫 last_error + reset is_running=False (FR-010, FR-011), (f) `recover_orphan(current_pid)` 偵測 stale lock 並 reset
- [ ] T007 [P] Write `tests/unit/live_tracking/test_store.py`：covers (a) load absent → None, (b) load valid envelope → strict pydantic parse, (c) `atomic_write` failure 模擬（fake `os.replace` raise）→ 既有檔案 byte 不變 (FR-009), (d) append-only invariant: 連續兩次 atomic_write，第二次的 trajectoryInline[:k] 必須 byte-equal 第一次 (FR-003), (e) load → mutate → write → reload sha256 確認改變 (mutable scope)

### Implementation

- [ ] T008 Implement `src/live_tracking/calendar.py`：純函數 `missing_trading_days(last_frame_date: date | None, today: date, *, start_anchor: date = date(2026,4,29)) -> list[date]`，內部用 `pandas_market_calendars.get_calendar("NYSE")`；當 `last_frame_date is None` 從 start_anchor 開始；當 `today < start_anchor` 回 `[]` (FR-007, edge case "尚未到起始日")
- [ ] T009 Implement `src/live_tracking/status.py`：Pydantic v2 `LiveTrackingStatus(BaseModel, extra='forbid')` 含 last_updated/last_frame_date/is_running/last_error/running_pid/running_started_at；class methods `load(path)`, `write(path)`, `mark_running(pid, started_at)`, `mark_succeeded(last_frame_date)`, `mark_failed(error_msg)`, `recover_orphan(current_pid)`（用 `psutil` 比對 pid_exists + create_time）(FR-010, FR-011, FR-015)
- [ ] T010 Implement `src/live_tracking/store.py`：`LiveTrackingStore` class with `load() -> EpisodeDetail | None`, `atomic_write(envelope)`；重用 `src/data_ingestion/atomic.py` `staging_scope`；reuse 009 `EpisodeDetail` from `src.inference_service.episode_schemas` (FR-001, FR-009)

### Acceptance criteria (Phase 2)

- T005~T007 RED first，T008~T010 GREEN 後 invariants：(INV-1, INV-2, INV-3 from data-model.md) 全綠
- ruff + mypy clean

---

## Phase 3: User Story 1 (P1) — 操作者手動觸發每日決策更新

**Goal**: 操作者在 Overview 點按鈕 → pipeline 跑 → NAV 線、權重、SMC 全部更新到今天

**Independent Test**: 乾淨環境 → POST /refresh → polling status → GET /episodes/{live_id} 回 trajectoryInline ≥ 1 frame → Overview 渲染（quickstart.md §4–§9）

### Tests first (RED) — Pipeline core

- [ ] T011 [P] [US1] Write `tests/unit/live_tracking/test_inference.py`：mock sb3 policy → `single_step_inference(policy, obs)` 回 `ActionResult(raw, normalized, log_prob, entropy)`；shape 驗證；確認沒有 episode loop (FR-020)
- [ ] T012 [P] [US1] Write `tests/unit/live_tracking/test_pipeline.py`：covers (a) no-op when missing_days==[] → `result.frames_appended == 0` + status `mark_succeeded` 不更新 last_frame_date (FR-008), (b) single missing day → 1 frame appended，reward 三元 present，SMC overlay 全段重算 (FR-007, FR-004), (c) multi-day backfill (5 days) → 5 frames，日期嚴格遞增，無跳號 (SC-002), (d) any step exception → status.last_error 三類前綴之一，artefact bytes 不變 (FR-009, FR-010, SC-005), (e) refresh while is_running → raise `RefreshInProgressError`
- [ ] T013 [P] [US1] Write `tests/integration/inference_service/test_live_pipeline_e2e.py`：用 `freezegun` 鎖 today=2026-05-08，stub OHLCV provider，真 PortfolioEnv + 真 store + 真 batch_compute_events；驗 (a) artefact 落地 schema 通過 EpisodeDetail.model_validate，(b) summary metrics 重算（finalNav / cumReturn / MDD / Sharpe / Sortino）非零 (FR-005), (c) `frames_appended == len(missing_days)` (SC-002)

### Implementation — Pipeline core

- [ ] T014 [US1] Implement `src/live_tracking/inference.py`：`single_step_inference(policy, obs) -> ActionResult` 包 `policy.predict` + `policy.evaluate_actions` 取 log_prob/entropy；不要重新建立 env，accept obs as plain ndarray (FR-020)
- [ ] T015 [US1] Implement `src/live_tracking/pipeline.py` skeleton：`DailyTrackerPipeline` dataclass holding store/status/calendar/policy/env/ohlcv_provider；method `run_once(today: date) -> PipelineResult`（先寫殼 + 階段 todo comments）
- [ ] T016 [US1] Implement pipeline step 1 — guard：read status；若 is_running raise；mark_running(pid, started_at)；持久化 status (FR-006)
- [ ] T017 [US1] Implement pipeline step 2 — fetch & no-op early return：`missing_days = calendar.missing_trading_days(last_frame_date, today)`；若 empty → mark_succeeded（last_frame_date 不變）+ 結構化 log + return (FR-007, FR-008)
- [ ] T018 [US1] Implement pipeline step 3 — per-day inference loop：reset env at last_frame state → step env with action from inference → 收 frame（含 reward 三元、action 四元、ohlcvByAsset 當日 bar）；跳出 loop 任一錯誤 → mark_failed("INFERENCE: ...") raise (FR-019, FR-020)
- [ ] T019 [US1] Implement pipeline step 4 — append + recompute：把新 frames append 到 trajectoryInline；對整段 trajectory 跑 6-asset `batch_compute_events`（重用 008）→ 覆蓋 smcOverlayByAsset (FR-004)
- [ ] T020 [US1] Implement pipeline step 5 — summary metrics：重算 `EpisodeSummary` 從整段 trajectory（finalNav / cumReturn / maxDrawdown / Sharpe / Sortino）(FR-005)
- [ ] T021 [US1] Implement pipeline step 6 — atomic write + status.mark_succeeded：呼叫 store.atomic_write；error → mark_failed("WRITE: ...") raise (FR-009)
- [ ] T022 [US1] Implement structured log line at pipeline complete/failure：`structlog.info("daily_tracker_pipeline_complete", ...)` 含 frames_appended / smc_zones_computed / pipeline_duration_ms / final_status / error_class (FR-026)
- [ ] T023 [US1] Implement `scripts/run_daily_tracker.py` CLI wrapper：`python scripts/run_daily_tracker.py --policy-run-id <id>` → 呼叫 `DailyTrackerPipeline.run_once(date.today())`；exit code 0/1

### Tests first (RED) — 005 endpoints

- [ ] T024 [P] [US1] Write `tests/contract/inference_service/test_live_openapi.py`：用 `openapi-spec-validator` 驗 `contracts/openapi-live-tracking.yaml` 自身有效；用 `schemathesis` 對 FastAPI app 跑 status 200 schema fuzzing (FR-018)
- [ ] T025 [P] [US1] Write `tests/integration/inference_service/test_live_endpoints.py`：FastAPI TestClient → covers (a) GET /live/status 首次 → 全 None + data_lag_days null, (b) POST /live/refresh first call → 202 + RefreshAcceptedResponse schema (FR-016), (c) 並發 POST /refresh 第二個 → 409 + RefreshConflictResponse + running_pid present (FR-006, SC-004), (d) GET /episodes 回 list 含 source 欄位 + OOS 在前 Live 在後 (FR-012), (e) GET /episodes/{live_id} → 讀 live_tracking.json 不快取 (FR-013), (f) GET /episodes/{oos_id} → 仍讀 OOS（不變動）(FR-014)

### Implementation — 005 endpoints

- [ ] T026 [US1] Refactor `src/inference_service/episodes.py`：rename `EpisodeStore` → `OOSEpisodeStore`；add `MultiSourceEpisodeStore` containing optional oos + live；`list_envelope()` merges; `get_envelope(id)` dispatches by `_live` suffix (FR-012, FR-013)
- [ ] T027 [US1] Add Pydantic DTOs to `src/inference_service/episode_schemas.py`：`LiveTrackingStatusResponse`, `RefreshAcceptedResponse`, `RefreshConflictResponse`, `EpisodeListItem.source: Literal["oos","live"]` (extra='forbid' 全部) (FR-015, FR-016, FR-012)
- [ ] T028 [US1] Implement `src/inference_service/live_endpoints.py`：FastAPI router；module-level `asyncio.Lock`；`POST /live/refresh` → 若 lock acquired by other → 409；否則 schedule BackgroundTasks 跑 `DailyTrackerPipeline.run_once(date.today())`；立即 return 202 with `pipeline_id=uuid4()`, `estimated_duration_seconds=max(8, len(missing_days)*1+2)` (FR-016, FR-006, R10)
- [ ] T029 [US1] Implement `GET /live/status` handler in `live_endpoints.py`：load LiveTrackingStatus → 計算 `data_lag_days = max(0, (today_utc - last_frame_date).days) if last_frame_date else None` → return LiveTrackingStatusResponse (FR-015, FR-027)
- [ ] T030 [US1] Wire up `app.py` lifespan: startup → load policy（既有）→ 建 `LiveTrackingStore` + `LiveTrackingStatus`（含 orphan recovery via psutil）→ 建 `MultiSourceEpisodeStore`（注入 oos + live）→ register `live_router`；startup log emit `live_tracking_status_recovered_orphan: <bool>` (R6)

### Tests first (RED) — 006 Gateway

- [ ] T031 [P] [US1] Write `services/gateway/src/test/java/.../EpisodeControllerLiveTest.java`：WireMock stub 005；covers (a) GET /api/v1/episodes/live/status proxy 200 schema 對齊 LiveTrackingStatusDto, (b) POST /api/v1/episodes/live/refresh 202 → RefreshAcceptedDto, (c) 005 回 409 → gateway 透傳 409 + body, (d) 005 timeout → gateway 502 (FR-017, FR-018)

### Implementation — 006 Gateway

- [ ] T032 [P] [US1] Add `services/gateway/src/main/java/.../dto/LiveTrackingStatusDto.java` (record)
- [ ] T033 [P] [US1] Add `services/gateway/src/main/java/.../dto/RefreshAcceptedDto.java` + `RefreshConflictDto.java` (records)
- [ ] T034 [US1] Extend `EpisodeClient.java`：add `Mono<LiveTrackingStatusDto> fetchLiveStatus()` + `Mono<RefreshAcceptedDto> triggerLiveRefresh()`；errors map to existing `InferenceServiceException` / `InferenceBusyException` (FR-017)
- [ ] T035 [US1] Extend `EpisodeController.java`：add `GET /api/v1/episodes/live/status` + `POST /api/v1/episodes/live/refresh`；status code 透傳 (FR-017)
- [ ] T036 [US1] Add two paths to `services/gateway/openapi.yaml` 對齊 `contracts/openapi-live-tracking.yaml` (FR-018)

### Tests first (RED) — Frontend Overview

- [ ] T037 [P] [US1] Write `apps/warroom/src/api/__tests__/episodes.test.ts`：mock fetch → covers `fetchLiveStatus()` 解析、`triggerRefresh()` 202 解析 + 409 錯誤分流
- [ ] T038 [P] [US1] Write `apps/warroom/src/hooks/__tests__/useLiveRefresh.test.tsx`：vi.useFakeTimers + react-query；covers (a) idle polling 60s, (b) mutation in-flight → switch to 3s polling (R11), (c) on success → invalidate episode-detail query, (d) 409 → toast「正在更新中」(FR-024)
- [ ] T039 [P] [US1] Write `apps/warroom/src/components/overview/__tests__/DataLagBadge.test.tsx`：covers N=0 → 「最新」、N=1 → 「1 天前」、N=7 → 「7 天前」、N=null → 「Live tracking 尚未啟動」 (FR-022, SC-003)
- [ ] T040 [P] [US1] Write `apps/warroom/src/components/overview/__tests__/LiveRefreshButton.test.tsx`：covers (a) idle → enabled, (b) is_running=true → disabled + spinner (FR-024), (c) click → onClick called once

### Implementation — Frontend Overview

- [ ] T041 [P] [US1] Add `apps/warroom/src/api/episodes.ts`：`fetchLiveStatus()`, `triggerRefresh()` (axios/fetch)
- [ ] T042 [P] [US1] Add zod schemas + mapper in `apps/warroom/src/api/envelopes.ts`：`LiveTrackingStatusSchema` (strict) + `toLiveTrackingStatus(dto)`
- [ ] T043 [US1] Implement `apps/warroom/src/hooks/useLiveRefresh.ts`：`useMutation` + `useQuery({ refetchInterval: isInflight ? 3000 : 60000 })`；on settle → `queryClient.invalidateQueries(['episode', liveId])`
- [ ] T044 [P] [US1] Implement `apps/warroom/src/components/overview/DataLagBadge.tsx` (FR-022)
- [ ] T045 [P] [US1] Implement `apps/warroom/src/components/overview/LiveRefreshButton.tsx`：includes loading spinner + disabled state + toast 失敗訊息（用 `last_error` 字串）(FR-023, FR-024, FR-025)
- [ ] T046 [US1] Modify `apps/warroom/src/pages/OverviewPage.tsx`：default episode id = live id；當 live status 仍 None → 顯示「Live tracking 尚未啟動，請按手動更新建立」guidance (FR-021)；加 header 容器塞 `<DataLagBadge>` + `<LiveRefreshButton>`

### Acceptance criteria (US1)

- SC-001 ✓ (首次 refresh 後 frames ≥ 1)
- SC-002 ✓ (N-day fill 連續無跳號)
- SC-003 ✓ (badge accuracy)
- SC-004 ✓ (409 < 1s)
- SC-006 ✓ (≤ 60s single day, ≤ 180s 7 days)

**🛑 MVP CHECKPOINT**: 完成 T001~T046 即可 demo User Story 1 完整流程。

---

## Phase 4: User Story 2 (P2) — OOS + Live 並存

**Goal**: EpisodeList 同時可見 OOS（不可變學術 baseline）+ Live（每日活成果）

**Independent Test**: GET /api/v1/episodes 回 2 筆，OOS 在前；點 OOS detail 5 次 sha256 相同（SC-008）；點 Live detail 隨更新變動

> 大部分基礎設施在 US1 已完成（MultiSourceEpisodeStore + EpisodeListItem.source）。本 Phase 補強 invariants。

### Tests first (RED)

- [ ] T047 [P] [US2] Write `tests/contract/episode_artifact/test_oos_immutable_hash.py`：連 5 次讀 OOS `episode_detail.json` + 連 5 次 GET /episodes/{oos_id} 回 body sha256 → 全相等 (SC-008, FR-014, **Constitution Principle I gate for OOS**)
- [ ] T048 [P] [US2] Write `tests/contract/live_tracking/test_append_only.py`：mock pipeline 跑兩次（today=D1 → today=D2），第二次後 `trajectoryInline[:len_after_D1]` byte-equal 第一次寫入內容 (FR-003, INV-3, **Constitution Principle I gate for Live**)
- [ ] T049 [P] [US2] Write `tests/integration/inference_service/test_episodes_dual_source.py`：fixtures: OOS artefact present + Live artefact 不存在 → list 回 1 筆；Live artefact 後續被建立 → list 回 2 筆 (OOS 在前) (FR-012)

### Implementation gates

- [ ] T050 [US2] Verify `MultiSourceEpisodeStore.list_envelope()` ordering invariant 在 T026 已正確實作；若不正確補 fix；對應 unit test
- [ ] T051 [US2] Verify GET /episodes/{live_id} 不走快取（每次 reload）— 在 T026 dispatch 中加 comment + 一條 unit test 驗證 mtime 變動後 response body 跟著變

### Acceptance criteria (US2)

- SC-007 ✓ (前端不分支即可渲染 OOS 與 Live — 由 T046 + T037 fixture 已驗證)
- SC-008 ✓ (T047 綠)
- INV-3, INV-5 (data-model.md) 綠

---

## Phase 5: User Story 3 (P2) — 失敗回滾與失敗訊息可見

**Goal**: pipeline 失敗時 artefact 不破損，前端顯示具體錯誤訊息（含失敗時間、原因摘要、再試入口）

**Independent Test**: 模擬 fetch 失敗 → POST /refresh → status.last_error 非空且字串開頭 `DATA_FETCH:` → 重整 Overview 看到 toast → 修復後再點「再試一次」成功 → 通知消失

### Tests first (RED)

- [ ] T052 [P] [US3] Write `tests/contract/live_tracking/test_atomic_rollback.py`：用 `unittest.mock.patch` 注入 `os.replace` raise OSError → 確認 (a) raise 回到 caller, (b) live_tracking.json mtime + sha256 與 patch 前完全相同 (FR-009, INV-2, SC-005)
- [ ] T053 [P] [US3] Write `tests/unit/live_tracking/test_error_classification.py`：對三種注入錯誤（fetch raise / inference raise / write raise）→ status.last_error 開頭分別為 `DATA_FETCH:` / `INFERENCE:` / `WRITE:` (R7)
- [ ] T054 [P] [US3] Write `apps/warroom/src/components/overview/__tests__/FailureToast.test.tsx`：given status.last_error="DATA_FETCH: yfinance ..."，render Overview → toast 顯示時間 + 原因 + 「再試一次」按鈕；點按鈕觸發 mutation (FR-025, SC-009)

### Implementation

- [ ] T055 [US3] Pipeline step error wrappers in `pipeline.py`: 用 try/except 對三段（fetch / inference / write）分別前綴 `DATA_FETCH:` / `INFERENCE:` / `WRITE:` 寫入 status.last_error (R7, FR-010)
- [ ] T056 [US3] Add `FailureToast` component logic to `LiveRefreshButton.tsx` (or new `FailureBanner.tsx`)：當 `status.last_error` 非 null → render persistent banner 含 last_updated 時間 + last_error 字串 + 「再試一次」button; success 後 toast 消失 (FR-025, FR-011)
- [ ] T057 [US3] Add quickstart §8 (failure rollback verification) 對應 docker compose 跑法（已寫於 quickstart.md）— 補上 `LIVE_TRACKER_FORCE_FETCH_ERROR` env 在 `pipeline.py` 處理

### Acceptance criteria (US3)

- SC-005 ✓ (T052 綠)
- SC-009 ✓ (T054 綠 + Overview 顯示 banner ≤ 5s after refresh)
- INV-2 (data-model.md) 綠

---

## Phase 6: Constitution Gate Tests (NON-NEGOTIABLE)

> 三條 gate test 是 PR merge 的硬閘，獨立分檔以利 CI selective run

- [ ] T058 [P] Already wrote in T047 — `tests/contract/episode_artifact/test_oos_immutable_hash.py` (Principle I, OOS scope) — re-run確認綠
- [ ] T059 [P] Already wrote in T048 — `tests/contract/live_tracking/test_append_only.py` (Principle I, Live scope) — re-run確認綠
- [ ] T060 Write `tests/contract/live_tracking/test_reward_parity.py`：fix seed; build a `PortfolioEnv` 兩份（pipeline 用 + parity reference 用）；feed 同 obs + 同 action；assert pipeline frame.reward.{returnComponent,drawdownPenalty,costPenalty} == reference reward 三元，tolerance 1e-9 (FR-019, INV-4, **Constitution Principle III gate**)

### Acceptance criteria (Phase 6)

- 三條 gate test 全綠才可推 PR
- pytest 跑 `-m "contract and (oos or live_tracking)"` 結果 all green

---

## Phase 7: Polish & Cross-cutting

- [ ] T061 [P] ruff + mypy clean across new files (`src/live_tracking/`, `src/inference_service/live_endpoints.py`, `src/inference_service/episodes.py` refactor)
- [ ] T062 [P] Coverage check: 新增程式碼 coverage ≥ 80%（pytest --cov=src/live_tracking --cov=src/inference_service.live_endpoints）
- [ ] T063 [P] Java：`./mvnw test` 全綠（含 T031 contract test）
- [ ] T064 [P] Frontend：`pnpm test` 全綠（含 T037–T040 + T054）
- [ ] T065 Docker compose smoke：`docker compose -f infra/docker-compose.gateway.yml up --build -d` < 60s healthy；對齊 quickstart.md §2~§3
- [ ] T066 Manual e2e per quickstart.md §4–§9：第一次 refresh → status polling → GET /episodes 回 2 筆 → Overview 渲染 OK
- [ ] T067 Trace FR coverage：`scripts/check_fr_coverage.py` 或人工掃 FR-001~FR-027 各對應 ≥ 1 task；附 `specs/010-live-tracking-dashboard/coverage-trace.md`（簡表）

---

## Dependencies & order

- Phase 1 (Setup) before all
- Phase 2 (Foundational) before Phase 3 (US1 import calendar/status/store)
- Phase 3 (US1) — MVP 範圍；T011~T046 內部依序：tests RED → impl GREEN
- Phase 4 (US2), Phase 5 (US3) 可在 US1 完成後並行（不同檔案）
- Phase 6 (Constitution gates) 必須在 Phase 3+4+5 之後（依賴 pipeline + endpoints 已落地）
- Phase 7 (Polish) 最後

### Parallel clusters

- T003 + T004 + T005~T007 + T011~T013 + T024~T025 + T031 + T037~T040 + T047~T049 + T052~T054 全部 [P] safe（不同檔案、無 import 相依）
- T032 + T033 同時（兩個獨立 Java DTO 檔）
- T041 + T042 + T044 同時（前端不同元件檔）

---

## FR coverage map

| FR | Tasks |
|----|-------|
| FR-001 | T002, T010 |
| FR-002 | T003 |
| FR-003 | T007, T048 |
| FR-004 | T012(b), T019 |
| FR-005 | T013, T020 |
| FR-006 | T016, T025(c), T028 |
| FR-007 | T001, T005, T008, T012(c), T017 |
| FR-008 | T012(a), T017 |
| FR-009 | T007(c), T021, T052 |
| FR-010 | T006(e), T055 |
| FR-011 | T006(e), T056 |
| FR-012 | T025(d), T026, T027, T049 |
| FR-013 | T025(e), T026, T051 |
| FR-014 | T025(f), T047 |
| FR-015 | T009, T027, T029 |
| FR-016 | T025(b), T027, T028 |
| FR-017 | T034, T035 |
| FR-018 | T024, T031, T036 |
| FR-019 | T060 |
| FR-020 | T011, T014 |
| FR-021 | T046 |
| FR-022 | T039, T044 |
| FR-023 | T045 |
| FR-024 | T038(d), T040, T045 |
| FR-025 | T045, T054, T056 |
| FR-026 | T022 |
| FR-027 | T029 |

## SC coverage map

| SC | Tasks |
|----|-------|
| SC-001 | T013, T066 |
| SC-002 | T012(c), T013 |
| SC-003 | T039, T066 |
| SC-004 | T025(c) |
| SC-005 | T052 |
| SC-006 | T013 (perf budget assertions), T066 |
| SC-007 | T046 (no-branch render), T066 |
| SC-008 | T047 (Constitution Principle I gate) |
| SC-009 | T054 |

## Out of scope (DO NOT TASK)

- GitHub Actions cron / 任何 workflow_dispatch 自動化（spec OUT OF SCOPE）
- PPO 重訓 / hyperparameter tune
- 多 policy 並行 live tracking
- 即時 streaming
- Zeabur 部署具體配置
- 修改 003 env / reward.py / observation shape
- 修改 008 SMC engine 內部
- 修改 009 build_episode_artifact.py（OOS one-shot，schema 共用但 pipeline 不複用）
- Episode 列表分頁（最多 2 筆 episode）
- fixture builder 重生（屬 task #28、後續 follow-up）
