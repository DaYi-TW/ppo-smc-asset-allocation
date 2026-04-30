# Tasks: 推理服務（005-inference-service）

**Branch**: `005-inference-service` | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

依 plan.md 之 Single project 結構。所有路徑相對 repo root。tests 與 src 同節奏推進（contract test 先於 implementation 屬 TDD lite）。

## Phase 1: Setup

- [ ] T001 在 `pyproject.toml` 新增 optional dependency group `[inference]`：`fastapi~=0.110, uvicorn[standard]~=0.29, sse-starlette~=2.0, prometheus-client~=0.20, pydantic~=2.6, orjson, PyYAML`，dev: `httpx, pytest-asyncio, openapi-spec-validator`
- [ ] T002 建立 `src/inference_service/__init__.py`、`__main__.py` (uvicorn 啟動入口) 骨架
- [ ] T003 [P] 建立 `tests/contract/`、`tests/integration/`、`tests/unit/` 目錄結構與 `conftest.py`
- [ ] T004 [P] 建立 CI step：`python -m inference_service dump-openapi --output specs/005-inference-service/contracts/openapi.yaml` + git diff 檢查（FR-017）

## Phase 2: Foundational (Blocking Prerequisites)

**所有 user stories 共用**

- [ ] T005 實作 `src/inference_service/config.py`：ServiceConfig dataclass + env var 解析 + 啟動驗證（plan §config）
- [ ] T006 實作 `src/inference_service/errors.py`：自訂例外類別（PolicyNotFoundError、PolicyIdExistsError、ObservationDimMismatchError 等）+ FastAPI exception handler（統一 ErrorResponse schema，contracts/error-codes.md）
- [ ] T007 實作 `src/inference_service/observability/logging.py`：JSONFormatter + getLogger helper；stdout 為 JSON、stderr 為 stack trace
- [ ] T008 實作 `src/inference_service/observability/metrics.py`：定義 prometheus-client Counter/Histogram/Gauge（data-model §8 表格）+ FastAPI middleware 自動記錄 latency
- [ ] T009 [P] [Unit] 實作 `tests/unit/test_config.py`：env var 解析、預設值、驗證錯誤
- [ ] T010 [P] [Unit] 實作 `tests/unit/test_logging.py`：JSON 欄位完整性、stack trace 不入 JSON
- [ ] T011 實作 `src/inference_service/schemas/`：Pydantic models — `infer.py` (InferenceRequest/Response, RewardComponents)、`episode.py` (EpisodeRequest/Response, EpisodeLogEntry, EpisodeSummary)、`policy.py` (PolicyMetadata, PolicyInfo, PolicyListResponse, PolicyLoadRequest, PolicyDeleteResponse)
- [ ] T012 實作 `src/inference_service/policies/handle.py`：PolicyHandle dataclass（policy_id, sb3 PPO instance, obs_dim, action_dim, metadata, loaded_at_utc, policy_path, inference_count）
- [ ] T013 實作 `src/inference_service/policies/loader.py`：從 zip 路徑 + 同目錄 metadata.json 載入 → PolicyHandle；處理 POLICY_LOAD_FAILED / POLICY_FILE_CORRUPT / POLICY_METADATA_MISSING 三種錯誤
- [ ] T014 實作 `src/inference_service/policies/registry.py`：PolicyRegistry（dict 包裝）+ register/unregister/get/list_ids/count；單例 via FastAPI dependency
- [ ] T015 實作 `src/inference_service/app.py`：FastAPI app factory + router 註冊 + lifespan event（啟動載入 default policy → registry）
- [ ] T016 [P] [Unit] 實作 `tests/unit/test_policy_handle.py`、`tests/unit/test_registry.py`

## Phase 3: User Story 1 - 對外提供 PPO 推理 API (P1) — MVP

**Goal**: `POST /v1/infer` 上線、單機 CPU 跑通、p99 < 50 ms。

**Independent Test**: 啟動服務 → curl POST 合法 obs → 200 + 7 維 action sum=1。

- [ ] T017 [US1] 實作 `src/inference_service/routers/ops.py`：`GET /healthz`, `GET /readyz`, `GET /metrics`（FR-011~FR-013）
- [ ] T018 [US1] 實作 `src/inference_service/routers/infer.py`：`POST /v1/infer` handler（async + asyncio.to_thread for policy.predict）
- [ ] T019 [US1] infer.py 中加 NaN 檢查、obs_dim 驗證、deterministic flag 處理（FR-001~FR-003）
- [ ] T020 [US1] infer.py 整合 metrics middleware：每筆推理寫 inference_requests_total + inference_latency_seconds
- [ ] T021 [P] [US1] [Contract] `tests/contract/test_openapi_validity.py`：`openapi_spec_validator.validate_spec(yaml.load("contracts/openapi.yaml"))` 不 raise
- [ ] T022 [P] [US1] [Contract] `tests/contract/test_infer_schema.py`：用 httpx + Pydantic 驗證 /v1/infer 200 / 400 回應 schema 與 openapi.yaml 一致
- [ ] T023 [P] [US1] [Integration] `tests/integration/test_health_metrics.py`：service 啟動後 healthz/readyz/metrics 三端點行為（FR-011~FR-013, SC-008）
- [ ] T024 [P] [US1] [Integration] `tests/integration/test_infer_byte_identical.py`：deterministic=true 同 obs 兩次推理 byte-identical（FR-020, SC-005）
- [ ] T025 [US1] [Integration] `tests/integration/test_concurrent_inference.py`：100 並發 + 10000 次推理 → p99 < 50 ms、p50 < 10 ms（SC-001, SC-006）
- [ ] T026 [US1] [Integration] `tests/integration/test_inference_errors.py`：obs dim mismatch → 400 + OBSERVATION_DIM_MISMATCH；NaN obs → 400 + OBSERVATION_NAN

**Checkpoint**: US1 完成 → 服務可作為單機推理 API 上線。

## Phase 4: User Story 2 - 完整 episode 推理與決策日誌 (P1)

**Goal**: `POST /v1/episode/run` 與 003 直接執行 byte-identical；`POST /v1/episode/stream` SSE 推送進度。

**Independent Test**: 1 年 episode < 5 秒；diff API 結果 vs 直接 import 003 結果 → 0 byte 差異。

- [ ] T027 [US2] 實作 `src/inference_service/services/episode_runner.py`：`run_episode(policy_handle, start, end, include_smc, seed, deterministic) -> tuple[list[dict], dict]`；內部 import 003 PortfolioEnv、跑 step loop、收集 info、用 003 `info_to_json_safe` 轉換
- [ ] T028 [US2] 實作 `src/inference_service/routers/episode.py`：`POST /v1/episode/run` handler（FR-004, FR-005）
- [ ] T029 [US2] 加日期範圍驗證：start < end、≤ episode_max_days、覆蓋 002 Parquet 範圍（DATA_NOT_AVAILABLE）
- [ ] T030 [US2] 計算 episode_summary：final_nav、peak_nav、max_drawdown、sharpe_ratio、sortino_ratio、total_return、annualized_return、annualized_volatility、num_trades、avg_turnover（data-model §5）
- [ ] T031 [US2] 實作 `POST /v1/episode/stream` SSE 端點 (sse-starlette EventSourceResponse)：每 step_chunk 發 `progress` event、結束發 `done` event、錯誤發 `error` event（FR-006）
- [ ] T032 [P] [US2] [Contract] `tests/contract/test_episode_schema.py`：response 對 EpisodeResponse / EpisodeLogEntry 嚴格驗證
- [ ] T033 [US2] [Integration] `tests/integration/test_episode_vs_env.py`：API 結果 vs 直接 import 003+004 跑 byte-identical（SC-004, FR-005）
- [ ] T034 [P] [US2] [Integration] `tests/integration/test_episode_reproducibility.py`：同參數兩次 run byte-identical（FR-021）
- [ ] T035 [US2] [Integration] `tests/integration/test_episode_stream.py`：SSE event 順序、id 遞增、最後一筆為 done
- [ ] T036 [US2] [Integration] `tests/integration/test_episode_perf.py`：1 年 < 5s、8 年 < 30s（SC-002）

**Checkpoint**: US2 完成 → 戰情室可拿到完整 episode trajectory + summary、可串流播放動畫。

## Phase 5: User Story 3 - Policy 版本管理與切換 (P2)

**Goal**: `/v1/policies` 三端點上線，可動態載入、切換、卸載而不重啟服務。

**Independent Test**: load → list 顯示兩筆 → infer 可指定 policy_id → delete 後 404。

- [ ] T037 [US3] 實作 `src/inference_service/routers/policies.py`：`GET /v1/policies`、`POST /v1/policies/load`、`DELETE /v1/policies/{policy_id}`（FR-007~FR-009）
- [ ] T038 [US3] policies.py 中：load 失敗區分 POLICY_LOAD_FAILED / POLICY_FILE_CORRUPT / POLICY_METADATA_MISSING / POLICY_ID_EXISTS
- [ ] T039 [US3] /v1/policies/load 完成後寫 policy_load_duration_seconds Histogram metric
- [ ] T040 [P] [US3] [Contract] `tests/contract/test_policies_schema.py`：3 端點 response 對 schema 嚴格驗證
- [ ] T041 [US3] [Integration] `tests/integration/test_policy_lifecycle.py`：完整 load → list 顯示 → infer 指定 id → delete → 404 流程
- [ ] T042 [US3] [Integration] `tests/integration/test_policy_load_errors.py`：4 種錯誤情境驗證
- [ ] T043 [US3] [Integration] `tests/integration/test_policy_default_unload.py`：刪除 default 後 /readyz 503；載入新 policy 後 /readyz 200

**Checkpoint**: US3 完成 → 論文 demo 可即時切換 baseline / ablation policy。

## Phase 6: User Story 4 - 健康檢查與可觀測性（P3）

**Goal**: 維運面達 production 標準（K8s probe、Prometheus、結構化 log）。

**Independent Test**: 1000 次推理後 metrics 計數正確、log 為合法 JSON。

- [ ] T044 [US4] 強化 `routers/ops.py`：`/readyz` 檢查 registry.count() ≥ 1、回 ReadyResponse 含 policies_loaded
- [ ] T045 [US4] 在 metrics.py 加 `process_resident_memory_bytes`、`process_cpu_seconds_total`（prometheus-client 內建 ProcessCollector）
- [ ] T046 [US4] 結構化 log：每筆 inference / episode / policy_load 寫 INFO log，欄位含 inference_id、policy_id、latency_ms、status_code（FR-014）
- [ ] T047 [US4] 錯誤 log：500 錯誤 stderr 寫完整 stack trace + error_id；JSON log（stdout）只寫 error_id + error_class
- [ ] T048 [P] [US4] [Integration] `tests/integration/test_metrics_correctness.py`：跑 1000 次推理 → /metrics 之 inference_requests_total ≥ 1000、histogram bucket 分佈符合預期（SC-001）
- [ ] T049 [P] [US4] [Integration] `tests/integration/test_log_structure.py`：捕捉 stdout、parse JSON 每行、驗證必填欄位

**Checkpoint**: US4 完成 → 服務可進 production K8s。

## Phase 7: Polish & Cross-Cutting Concerns

**Cross-cutting，不綁特定 user story**

- [ ] T050 實作 `python -m inference_service dump-openapi --output <path>` CLI 子命令；CI 跑此命令並 git diff 檢查（FR-017、R8）
- [ ] T051 撰寫 `Dockerfile`：python:3.11-slim、`pip install -e ".[inference]"`、預設 `CMD ["python", "-m", "inference_service"]`
- [ ] T052 撰寫 `docs/inference_service_deploy.md`：K8s deployment YAML 範例（liveness/readiness/resources/envs）+ Prometheus ServiceMonitor 範例
- [ ] T053 [P] 跑 SC-003 memory leak 驗證：1M 次推理後 RSS 增長 < 50 MB；寫 `tests/integration/test_memory_leak.py`
- [ ] T054 [P] 跑 SC-009 OpenAPI validator pipeline：`openapi-spec-validator contracts/openapi.yaml` + `openapi-generator-cli generate -i contracts/openapi.yaml -g java -o /tmp/java_stub` 兩步驟皆 exit 0
- [ ] T055 確認測試覆蓋率 ≥ 85%（SC-007）：`pytest --cov=src/inference_service --cov-report=term-missing --cov-fail-under=85`
- [ ] T056 重新跑全部 quickstart.md 8 個情境，確認皆 pass
- [ ] T057 Final Constitution Check：對照 plan.md 五大原則，文件化任何後期偏離（無偏離則填 N/A）

## Dependencies

```text
Phase 1 Setup        → Phase 2 Foundational
Phase 2 Foundational → Phase 3 (US1) ─┐
                                       ├→ Phase 7 Polish
Phase 2 Foundational → Phase 4 (US2) ──┤
Phase 2 Foundational → Phase 5 (US3) ──┤
Phase 2 Foundational → Phase 6 (US4) ──┘
```

US1, US2, US3, US4 彼此獨立可平行；推薦順序為 P1（US1 → US2）→ P2（US3）→ P3（US4）。

## Parallel Execution 範例

Phase 2 結束後：
```bash
# 三個 P1/P2/P3 stream 可同時開工（建議單人專案先 P1）
git worktree add ../inference-us1 005-inference-service && cd ../inference-us1 && # T017-T026
git worktree add ../inference-us2 005-inference-service && cd ../inference-us2 && # T027-T036
git worktree add ../inference-us3 005-inference-service && cd ../inference-us3 && # T037-T043
```

## Implementation Strategy

**MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1) — 對外提供單筆推理。論文 demo 視覺化必須額外完成 Phase 4 (US2)。

**遞增交付**:
1. **MVP (US1)**: 服務啟動 + /healthz + /readyz + /v1/infer + /metrics + 100 並發 latency 達標
2. **+US2**: episode 推理 + SSE → 戰情室可顯示完整決策軌跡
3. **+US3**: 多 policy 切換 → 論文 baseline vs ablation 即時對比
4. **+US4**: production-grade observability → K8s 部署
5. **Polish**: Docker + docs + perf/memory benchmark
