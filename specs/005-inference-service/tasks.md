---
description: "Tasks for 005 推理服務（Inference Service）— C-lite 版"
---

# Tasks: 推理服務（005-inference-service）— C-lite 版

**Input**: Design documents at `specs/005-inference-service/`
**Prerequisites**: spec.md（2026-05-06 重寫版）、plan.md、research.md、data-model.md、contracts/openapi.yaml、contracts/error-codes.md、quickstart.md

**Tests**: 是。Coverage ≥ 85%（同 008 標準）。Test-first（red → green）。Phase 7 contract test 是本 feature 的 invariant — 不可省。

**Organization**: 任務依 plan §Phase Plan 的 7 個 phase 排序，每個 implementation task 之前先列對應 test task（TDD red → green）。`[P]` 標 parallel-safe（不同檔案、無相依）。每個 task ≤ 30 分鐘可獨立 commit。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**：可並行（不同檔案、不相依未完成 task）
- **[USx]**：對應 spec.md User Story x
- 路徑為 repo root 相對路徑（`src/`、`tests/`、`infra/`、`pyproject.toml`）

## Path Conventions

Single project（與 002 / 003 / 004 / 008 一致）：
- 程式碼：`src/inference_service/`
- 測試：`tests/{unit,integration,contract}/inference_service/`
- 容器：`infra/Dockerfile.inference`、`infra/docker-compose.inference.yml`

---

## Phase 1: Setup（pyproject + skeleton）

**Goal**：把 dependency group + 空殼模組就位，`python -m inference_service --help` 不噴錯，後續所有 phase 才有地方寫。
**Independent Test**：`pip install -e ".[inference]"` 成功；`pytest tests/unit/inference_service/ --collect-only` 能 import。

- [ ] T001 在 `pyproject.toml` 新增 `[project.optional-dependencies] inference = [...]` group（fastapi~=0.115、uvicorn[standard]~=0.32、apscheduler~=3.10、redis[hiredis]~=5.0、pytz~=2024.2、python-json-logger）。對應 plan §Phase 1 / FR-013、FR-014。
- [ ] T002 [P] 在 `pyproject.toml` 新增 `inference-dev` extras（pytest-asyncio、httpx、fakeredis~=2.26、testcontainers[redis]~=4.8、openapi-spec-validator）。對應 plan §Phase 7 測試需求。
- [ ] T003 [P] 建立 `src/inference_service/__init__.py`（空檔 + `__version__ = "0.1.0"`）與 `src/inference_service/__main__.py`（`raise SystemExit("not yet implemented")` stub）。
- [ ] T004 [P] 建立空殼檔 `src/inference_service/{config,handler,scheduler,redis_io,app,schemas}.py`，每檔放 module docstring + `pass` 即可（後續 phase 填內容）。
- [ ] T005 [P] 建立 `tests/{unit,integration,contract}/inference_service/__init__.py` + 共用 `conftest.py`（先放 fixture skeleton：`def policy_path()`、`def data_root()`，標 `pytest.skip("filled in T009")`）。
- [ ] T006 [P] 在 `pyproject.toml` 的 `[project.scripts]`（如已存在）或新建 `[project.entry-points]`，加入 `inference-service = "inference_service.__main__:main"`（`main()` 暫為 stub 函式回傳 0）。
- [ ] T007 跑 `pip install -e ".[inference,inference-dev]"` 驗證 dependency 鎖定成功；提交 commit「005 Phase 1 skeleton」。

---

## Phase 2: Config + handler core（共用 inference handler）

**Goal**（FR-001 / FR-003 / FR-006 / FR-007 / G-I-1 / G-I-3 / G-III-3）：建立 `ServiceConfig` + `PredictionPayload` Pydantic schema + `run_inference()` async handler；scheduled / manual 兩條入口共用同一 handler，asyncio.Lock 互斥。
**Independent Test**：mock policy + tiny dataset 跑 unit test，驗證兩次 call byte-identical（SC-007）+ lock 真互斥。

### Tests for Phase 2 (RED)

- [ ] T008 [P] [US1] 寫 `tests/unit/inference_service/test_config.py`：用 `monkeypatch.setenv` 注入 `POLICY_PATH` / `DATA_ROOT` / `REDIS_URL`，驗證 `ServiceConfig()` 載入成功；驗證缺欄位、空字串、不存在路徑時 `ValidationError` raise。對應 data-model §1。
- [ ] T009 [P] [US1] 在 `tests/unit/inference_service/conftest.py` 寫 `tiny_policy_run` fixture（指向 repo `runs/20260506_004455_659b8eb_seed42/final_policy.zip` + `data/raw/`），改之前 T005 的 skip 為實值。
- [ ] T010 [P] [US1] 寫 `tests/unit/inference_service/test_schemas.py`：驗證 `PredictionPayload.model_validate(predict_py_json)` 成功（包含 `triggered_by` / `inference_id` / `inferred_at_utc` 三個新欄位）；驗證 `target_weights` 7 維 sum≈1 在 `[0,1]` 內。對應 data-model §2 / FR-006 / FR-007。
- [ ] T011 [US1] 寫 `tests/unit/inference_service/test_handler_mutex.py`：兩個 `asyncio.create_task(run_inference("manual"))` 並發 await，驗證實際序列化（第二個 latency ≥ 第一個 duration），且回傳兩個 inference_id 不同。對應 plan §Risks 觸發互斥 / FR-003。
- [ ] T012 [US1] 寫 `tests/unit/inference_service/test_handler_reproducibility.py`：相同 config 跑兩次 `run_inference("manual")`，assert `target_weights` byte-identical（dict equality + 每維 `==` 不用 `np.isclose`）。對應 SC-007 / G-I-3。

### Implementation for Phase 2 (GREEN)

- [ ] T013 [US1] 在 `src/inference_service/config.py` 實作 `ServiceConfig(BaseSettings)`：14 個欄位對齊 data-model §1（policy_path、data_root、redis_url、schedule_cron、schedule_timezone、include_smc、seed、redis_channel、redis_key、redis_ttl_seconds、host、port、log_level）；加 `field_validator` 驗證 policy_path 存在 + `.zip` 結尾、data_root 至少有 1 個 `*.parquet`、`schedule_cron` 用 `CronTrigger.from_crontab` pre-validate。讓 T008 轉綠。
- [ ] T014 [P] [US1] 在 `src/inference_service/schemas.py` 實作 `TargetWeights`、`PredictionContext`、`PredictionPayload` Pydantic 2 model，欄位順序 byte-identical 對齊 `predict.py` 既有 JSON（再加 `triggered_by`/`inference_id`/`inferred_at_utc`）。讓 T010 轉綠。
- [ ] T015 [US1] 在 `src/inference_service/handler.py` 實作 `InferenceState` dataclass（lock、policy、env_factory、last_inference_at_utc、last_inference_id、inference_count、inference_failure_count）+ `init_state(config) -> InferenceState`（eager `PPO.load`，env_factory 用 closure）。對應 data-model §5 / G-I-2。
- [ ] T016 [US1] 在 `src/inference_service/handler.py` 實作 `async def run_inference(state, triggered_by) -> PredictionPayload`：`async with state.lock`、build env、跑到資料尾、收 final action、走 `env.process_action`（保留 G-III-3）、序列化成 PredictionPayload + 填 `triggered_by` / `inference_id=uuid4()` / `inferred_at_utc=now()`、更新計數器。讓 T011、T012 轉綠。
- [ ] T017 [US1] 跑 `pytest tests/unit/inference_service/ -v`，全綠後 commit「005 Phase 2 config + handler core」。

---

## Phase 3: HTTP layer（FastAPI app + 4 endpoints）

**Goal**（FR-001 / FR-008 / FR-009 / G-V-2）：把 handler 包成 FastAPI app，4 個 endpoint：`POST /infer/run`、`GET /infer/latest`、`GET /healthz`、`GET /openapi.json`（FastAPI 自動）。
**Independent Test**：httpx + fakeredis，4 endpoints 行為符合 contracts/openapi.yaml。

### Tests for Phase 3 (RED)

- [x] T01& [P] [US2] 寫 `tests/integration/inference_service/test_endpoint_infer_run.py`：`AsyncClient` `POST /infer/run`，assert 200 + payload `triggered_by="manual"`；同時送 2 個並發請求，第二個應回 200（排隊）或 409 INFERENCE_BUSY。對應 FR-001 / User Story 2。
- [x] T01& [P] [US3] 寫 `tests/integration/inference_service/test_endpoint_infer_latest.py`：先 `POST /infer/run` 成功一次，再 `GET /infer/latest` assert 200 + payload；剛啟動未跑過時 assert 404 + `code: NO_PREDICTION_YET`。對應 FR-008 / User Story 3。
- [x] T02& [P] [US4] 寫 `tests/integration/inference_service/test_endpoint_healthz.py`：service ready 時 `/healthz` 200 + `{status:"ok",policy_loaded:true,redis_reachable:true}`；強制 `state.policy=None` 時 503 + `{status:"degraded",policy_loaded:false}`。對應 FR-009 / User Story 4。
- [x] T02& [P] [US2] 寫 `tests/integration/inference_service/test_error_responses.py`：驗證 ErrorResponse schema（code/message/error_id/timestamp_utc）對齊 contracts/error-codes.md，stack trace 不洩漏到 response body（FR-012）。

### Implementation for Phase 3 (GREEN)

- [x] T02& [US2] 在 `src/inference_service/app.py` 實作 `create_app(config: ServiceConfig) -> FastAPI`：lifespan startup eager `init_state` + 註冊 scheduler（先 stub 留空 callback）；shutdown 不做事。對應 plan §Phase 3。
- [x] T02& [US2] 在 `src/inference_service/app.py` 加 `POST /infer/run` route：呼叫 `handler.run_inference(state, "manual")`、回 PredictionPayload；catch `LockTimeout` → 409 INFERENCE_BUSY；catch generic Exception → 500 INFERENCE_FAILED + uuid error_id（stderr stack）。讓 T018 轉綠。
- [x] T02& [US3] 在 `src/inference_service/app.py` 加 `GET /infer/latest` route：呼叫 `redis_io.get_latest`（Phase 5 才填，先用 dict 先 stub）、回 PredictionPayload；空回 404 NO_PREDICTION_YET，過期回 404 PREDICTION_EXPIRED。讓 T019 轉綠（用 fakeredis）。
- [x] T02& [US4] 在 `src/inference_service/app.py` 加 `GET /healthz` route：回 `HealthResponse{status,uptime_seconds,policy_loaded,redis_reachable,last_inference_at_utc,next_scheduled_run_utc}`；degraded 時回 503。讓 T020 轉綠。
- [x] T02& [US2] 在 `src/inference_service/__main__.py` 改寫 `main()`：parse args、`uvicorn.run(create_app(ServiceConfig()), host=cfg.host, port=cfg.port)`。
- [x] T02& [US2] 跑 `pytest tests/integration/inference_service/test_endpoint_*.py -v`，全綠後 commit「005 Phase 3 HTTP layer」。

---

## Phase 4: Scheduler（APScheduler cron + DST + mutex）

**Goal**（FR-002 / FR-010 / SC-002 / SC-006）：APScheduler `AsyncIOScheduler` + `pytz.timezone("America/New_York")` cron trigger，與 FastAPI 同 event loop，失敗不停 scheduler。
**Independent Test**：mock APScheduler 把 trigger 改成 1 秒後，驗證 fire；模擬 DST 邊界 next_run_time 計算。

### Tests for Phase 4 (RED)

- [x] T028 [P] [US1] 寫 `tests/integration/inference_service/test_scheduler_basic.py`：把 `SCHEDULE_CRON="* * * * *"` 起 service，等 90 秒內收到 1 次 `scheduled_trigger_fired` log + 1 次 `inference_completed`，assert payload `triggered_by="scheduled"`。對應 FR-002 / User Story 1。
- [x] T029 [P] [US1] 寫 `tests/integration/inference_service/test_scheduler_dst.py`：用 freezegun 把時間設到 2026-03-08 ET 02:30（DST spring-forward 前一日），讀 `scheduler.get_jobs()[0].next_run_time`，assert 跨 DST 後仍指向 16:30 ET（UTC offset 從 -5 變 -4）；同樣測 2026-11-01 fall-back。對應 plan §Risks DST。
- [x] T030 [P] [US1] 寫 `tests/integration/inference_service/test_scheduler_failure_recovery.py`：mock `run_inference` 第一次 raise，第二次 OK；assert scheduler 持續活著、第二次 trigger 仍 fire。對應 FR-010 / SC-006。

### Implementation for Phase 4 (GREEN)

- [x] T031 [US1] 在 `src/inference_service/scheduler.py` 實作 `init_scheduler(state, config, redis_publisher) -> AsyncIOScheduler`：用 `AsyncIOScheduler()` + `CronTrigger.from_crontab(config.schedule_cron, timezone=pytz.timezone(config.schedule_timezone))`；callback 內 `await run_inference(state, "scheduled")` + `await redis_publisher(payload)` + log `scheduled_trigger_fired` / `scheduled_inference_failed`。讓 T028、T030 轉綠。
- [x] T032 [US1] 在 `app.py` lifespan startup 註冊 scheduler、shutdown 停 scheduler；確保與 uvicorn event loop 同 loop（不開 thread）。
- [x] T033 [US1] 跑 `pytest tests/integration/inference_service/test_scheduler_*.py -v`，全綠後 commit「005 Phase 4 scheduler + DST」。

---

## Phase 5: Redis publisher + LatestCache

**Goal**（FR-004 / FR-005 / FR-011 / SC-004）：async redis client 包 `publish_prediction` + `get_latest`，publish 失敗 ≠ inference 失敗（解耦）。
**Independent Test**：testcontainers 真 redis pub/sub round-trip 驗證。

### Tests for Phase 5 (RED)

- [x] T034 [P] [US1] 寫 `tests/integration/inference_service/test_redis_publish.py`（用 `testcontainers[redis]`）：起真 `redis:7-alpine`，先 `SUBSCRIBE predictions:latest`，呼叫 `publish_prediction(payload)`，assert subscriber 收到 byte-identical JSON。對應 FR-004 / SC-004。
- [x] T035 [P] [US3] 寫 `tests/integration/inference_service/test_redis_latest_cache.py`：`publish_prediction` 後 `GET key predictions:latest` assert TTL ∈ (604790, 604800]；`fakeredis` `expire(key, 0)` 後 `get_latest()` 回 None。對應 FR-005 / data-model §8。
- [x] T036 [P] [US1] 寫 `tests/unit/inference_service/test_redis_publish_failure.py`（fakeredis）：mock client `.publish()` raise `RedisError`，assert `publish_prediction` 不 raise（吞掉 + log warning）；assert `set()` 仍嘗試呼叫。對應 FR-011。

### Implementation for Phase 5 (GREEN)

- [x] T037 [US1] 在 `src/inference_service/redis_io.py` 實作 `class RedisIO` 封裝 `redis.asyncio.Redis.from_url(config.redis_url)`：`async def publish_prediction(payload: PredictionPayload)`（先 `await client.set(key, json, ex=ttl)`，再 `await client.publish(channel, json)`，兩個動作各自 try/except + log）；`async def get_latest() -> PredictionPayload | None`（`GET` + Pydantic validate，過期回 None）；`async def ping() -> bool`（給 healthz 用）。讓 T034、T035、T036 轉綠。
- [x] T038 [US1] 把 `redis_io.RedisIO` 接到 `app.py` lifespan + scheduler callback：`POST /infer/run` 完成後呼叫 `await redis_io.publish_prediction(payload)`（publish 失敗仍回 200）；`GET /infer/latest` 走 `redis_io.get_latest`；`GET /healthz` 用 `redis_io.ping()` 填 `redis_reachable`。
- [x] T039 [US1] 跑 `pytest tests/integration/inference_service/test_redis_*.py tests/unit/inference_service/test_redis_*.py -v`，全綠後 commit「005 Phase 5 redis publisher + cache」。

---

## Phase 6: Dockerfile + docker-compose（部署封裝）

**Goal**（FR-013 / FR-014 / FR-015 / SC-001 / SC-008）：image build 時把 policy + parquet copy 進去（immutable artifact），cold start ≤ 60s。
**Independent Test**：本機 `docker compose up` → `/healthz` 200 → `POST /infer/run` 90s 內 200。

- [ ] T040 [P] [US1] 寫 `infra/Dockerfile.inference`：`FROM python:3.11-slim` → install build deps → `COPY pyproject.toml requirements-lock.txt ./` → `pip install .[inference]` → `COPY src/ ./src/` → `ARG POLICY_RUN_ID` + `COPY runs/${POLICY_RUN_ID}/final_policy.zip /app/runs/${POLICY_RUN_ID}/` → `COPY data/raw /app/data/raw` → `CMD ["python","-m","inference_service"]`。對應 plan §Phase 6。
- [ ] T041 [P] [US1] 寫 `infra/docker-compose.inference.yml`：`python-infer` service（build context 指 root、`build-args: POLICY_RUN_ID`）+ `redis:7-alpine` sidecar；env var pass `POLICY_PATH=/app/runs/${POLICY_RUN_ID}/final_policy.zip`、`DATA_ROOT=/app/data/raw`、`REDIS_URL=redis://redis:6379/0`；healthcheck `curl -f http://localhost:8000/healthz`；`depends_on: {redis: {condition: service_healthy}}`。
- [ ] T042 [P] [US1] 寫 `infra/.dockerignore`（排除 `tests/`、`docs/`、`.git/`、`runs/*/checkpoints*` 等大目錄；只保留指定 `runs/<run_id>/final_policy.zip`）。
- [ ] T043 [US1] Smoke test：`docker compose -f infra/docker-compose.inference.yml --build-arg POLICY_RUN_ID=20260506_004455_659b8eb_seed42 up -d` → `curl /healthz` → `time curl -X POST /infer/run`（記錄 latency 必須 ≤ 90s）；對應 SC-001 / SC-008 cold start。
- [ ] T044 [US1] commit「005 Phase 6 docker-compose + Dockerfile」。

---

## Phase 7: Tests + Polish（contract test + lint + coverage）

**Goal**（G-V-2 / SC-005 / SC-007 / Coverage ≥ 85%）：contract test 為本 feature 核心 invariant — schema 與 `predict.py` byte-identical。完成 ruff / mypy / coverage 收尾。
**Independent Test**：跑 `pytest --cov=src/inference_service --cov-fail-under=85` + `ruff check` + `mypy` 全綠。

### Contract tests (RED → GREEN must hold)

- [ ] T045 [P] [US1] 寫 `tests/contract/inference_service/test_openapi_schema.py`：載 `specs/005-inference-service/contracts/openapi.yaml`，用 `openapi_spec_validator.validate_spec` 驗證 schema 合法；assert 4 個 path 都存在（`/infer/run`、`/infer/latest`、`/healthz`、`/openapi.json`）。對應 plan G-V-2。
- [ ] T046 [P] [US1] 寫 `tests/contract/inference_service/test_prediction_schema_parity.py`（核心 invariant）：用同 policy + 同資料快照，先呼叫 `python -m ppo_training.predict --policy ... --as-of ...` 產 ground-truth JSON；再起 service 跑 `POST /infer/run`；對 diff 兩份 dict — 除了 `triggered_by` / `inference_id` / `inferred_at_utc` 三個新欄位、其他欄位 byte-identical（`assert d1 == d2` 用 `dict.pop` 清掉新欄位後）。對應 SC-005 / SC-007 / FR-006 / G-I-3。
- [ ] T047 [P] [US1] 寫 `tests/contract/inference_service/test_error_response_contract.py`：對每個 error code（INFERENCE_BUSY、NO_PREDICTION_YET、PREDICTION_EXPIRED、POLICY_NOT_LOADED、REDIS_UNREACHABLE、INFERENCE_FAILED）構造對應條件，assert HTTP status code + body schema 對齊 `contracts/error-codes.md` §錯誤碼字典。

### Polish

- [ ] T048 [P] [US1] 跑 `ruff check src/inference_service/ tests/{unit,integration,contract}/inference_service/` 修到全綠；`ruff format` 套排版。
- [ ] T049 [P] [US1] 跑 `mypy src/inference_service/`（用 002 既有 mypy 配置）修到 0 error；如有 stable_baselines3 / gymnasium type stub 缺，加 `# type: ignore[import-untyped]` 並紀錄於 plan §Risks。
- [ ] T050 [P] [US1] 跑 `pytest tests/{unit,integration,contract}/inference_service/ --cov=src/inference_service --cov-report=term-missing --cov-fail-under=85`，補測試直到 ≥ 85%。
- [ ] T051 [P] [US1] 把 `quickstart.md` 「常見錯誤排除」表格末尾驗證一次（每個症狀至少跑出一次）；發現有 quickstart 寫錯時回頭改 quickstart.md（不改 spec/plan）。
- [ ] T052 [P] [US1] 在 repo root `README.md` 加一節「How to run inference service locally」（≤ 15 行），指向 `quickstart.md` Path A。
- [ ] T053 [US1] 最終 commit「005 Phase 7 contract tests + polish + coverage 85%」；確認 `git status` 乾淨、`pytest` 全綠、ruff/mypy 全綠。

---

## Dependencies

完成順序（user story 完成度視角）：

```text
Phase 1 (T001-T007) Setup
  └─▶ Phase 2 (T008-T017) US1 handler core   ◀── Reproducibility (G-I) 在這裡先收
        └─▶ Phase 3 (T018-T027) US2/US3/US4 endpoints
              └─▶ Phase 4 (T028-T033) US1 scheduler   ◀── 完整 daily flow
                    └─▶ Phase 5 (T034-T039) US1/US3 redis publisher + cache
                          └─▶ Phase 6 (T040-T044) US1 deploy
                                └─▶ Phase 7 (T045-T053) contract + polish
```

**MVP 切點**：Phase 2 + Phase 3 即可手動驗證 US2（POST /infer/run → 200）；Phase 4 上線後自動 daily（US1 完成）；Phase 5 上線後 US3 + War Room 接得起來。Phase 6/7 屬部署 + 收尾。

**Story 之間的相依**：
- US1（scheduled）依賴 US2 同個 handler（Phase 2）+ scheduler（Phase 4）
- US3（GET latest）依賴 Phase 5 redis cache
- US4（healthz）獨立、Phase 3 即可完成

## Parallel execution examples

**Phase 1 並行**：T002、T003、T004、T005、T006 可同時跑（不同檔案）。

**Phase 2 並行**：T008、T009、T010 三個 RED test 可同時寫；T014（schemas）可與 T013（config）並行；T015 / T016 必須在 T013 / T014 後序列。

**Phase 3 並行**：T018、T019、T020、T021 四個 endpoint test 同時寫；T023、T024、T025 因都改 `app.py` 必須序列。

**Phase 4 並行**：T028、T029、T030 三個 scheduler test 同時寫。

**Phase 5 並行**：T034、T035、T036 三個 redis test 同時寫；T037 為單一檔案實作，序列。

**Phase 6 並行**：T040（Dockerfile）、T041（compose）、T042（dockerignore）三檔同時寫。

**Phase 7 並行**：T045、T046、T047 三個 contract test 同時寫；polish T048~T052 全部不同檔案，並行。

## Acceptance Criteria（對齊 contracts/ invariants）

每個 phase 的合格標準對應到 contracts/ 與 spec.md 的具體 invariant：

| Gate / SC / FR | 對應 task | 驗證方式 |
|---|---|---|
| **SC-005** schema parity with predict.py | T046 | dict diff（清掉 3 新欄位後 `==`） |
| **SC-007** byte-identical reproducibility | T012、T046 | dict equality（容差 0.0） |
| **FR-003** mutex | T011 | concurrent await latency assertion |
| **FR-006** schema 對齊 | T010、T046 | Pydantic validate + diff |
| **FR-008** GET /infer/latest 行為 | T019 | 200 / 404 / TTL expired 三條 path |
| **FR-009** /healthz | T020、T025 | 200 / 503 + payload 欄位完整 |
| **FR-010** scheduler 失敗不停 | T030 | 第二次 trigger 仍 fire |
| **FR-011** publish 失敗 ≠ inference 失敗 | T036 | publish raise 不 propagate |
| **SC-001** docker-compose 90s 內可用 | T043 | smoke test latency 量測 |
| **SC-002** DST safety | T029 | freezegun 模擬 spring/fall 邊界 |
| **SC-008** cold start ≤ 60s | T043 | `time docker compose up` |
| **G-V-2** OpenAPI 對齊 | T045 | openapi-spec-validator |
| **Coverage ≥ 85%** | T050 | pytest-cov fail-under |

## Out of Scope（明確不排）

對齊 spec.md FR-016 / plan §Out of Scope：

- **fixture builder simplification**（屬 task #28、feature 007 follow-up，不在本 feature）
- **PPO retune / 重訓**（屬 003 / 004，008 完成後另起 feature）
- **Spring Gateway**（屬 006，本 feature 完成後馬上做）
- **前端 LivePredictionCard 接線**（屬 007 收尾，與 006 一起）
- **Kafka / Prometheus / TLS / JWT**（明確排除，見 plan §Out of Scope）
- **multi-policy reload / episode replay endpoint**（feature 005 舊版範圍，已移除）
- **多 replica horizontal scaling**（mutex 設計就是 single-instance）

## Implementation Strategy

**MVP first（增量交付）**：

1. **Iteration 1（Phase 1+2）**：service 啟動、handler 能跑、unit test 全綠 — 不對外暴露 HTTP，純 library 形式驗證 Reproducibility。
2. **Iteration 2（Phase 3）**：手動 `POST /infer/run` 可在本機跑通，httpx integration test 全綠 — 已可當 demo 用（只缺 daily 自動化）。
3. **Iteration 3（Phase 4+5）**：scheduler + redis 接好，整套 daily flow 完成 — 可接 006 / 007。
4. **Iteration 4（Phase 6）**：docker-compose 跑通 — 可給其他人 clone 後 `docker compose up` 直接看 demo。
5. **Iteration 5（Phase 7）**：contract test + coverage + ruff/mypy 收尾、commit「ready for 006」。

每個 iteration 都可獨立 demo / 獨立 review，符合「每個 task ≤ 30 分鐘 + 可獨立 commit」原則。
