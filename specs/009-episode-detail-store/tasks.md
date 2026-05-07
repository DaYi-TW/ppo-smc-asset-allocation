# Tasks: PPO Episode Detail Store

**Feature**: 009-episode-detail-store
**Branch**: `009-episode-detail-store`
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md) | **Contracts**: [openapi-episodes.yaml](contracts/openapi-episodes.yaml)

> 排序原則：Test-first（紅 → 綠）；同檔案的 implementation 合併以保持 ≤ 30 分鐘粒度；不同檔案標 [P]。

---

## Phase 1：Setup

- [ ] T001 確認 branch `009-episode-detail-store` 已 checkout，跑 `pytest -q tests/unit tests/integration tests/contract` baseline 全綠（不可帶入 pre-existing failure）
- [ ] T002 [P] 在 `pyproject.toml` 確認 `pyarrow >= 17`、`pydantic >= 2`、`openapi-spec-validator` 已在 dev extras（缺則加；不動 inference extras）
- [ ] T003 [P] 在 `apps/warroom/package.json` 確認 `zod` 在 dependencies（既有則跳）

---

## Phase 2：Foundational（blocking 全部 user story）

- [ ] T004 在 `src/inference_service/schemas.py` 新增 pydantic 模型：`EpisodeSummary`、`EpisodeDetail`、`EpisodeListEnvelope`、`EpisodeDetailEnvelope`、`TrajectoryFrame`、`WeightAllocation`、`RewardSnapshot`、`RewardSeries`、`RewardCumulativePoint`、`SMCSignals`、`OHLCV`、`ActionVector`、`SMCOverlay` 與其 子型（SwingPoint / FVGZone / OBZone / StructureBreak）；全部 `model_config = ConfigDict(extra="forbid")`，對齊 contracts/openapi-episodes.yaml
- [ ] T005 [P] 在 `tests/unit/inference_service/test_episode_schemas.py` 為 T004 加 schema 驗證：happy payload 通過、缺欄位 / 多欄位 / 違反 reward invariant 都失敗（先 RED）

---

## Phase 3：User Story 2 — Evaluator trajectory.parquet（Priority: P2）

> P2 在 P1 之前實作，因為 P1（artefact）依賴 P2 的 trajectory。

**Story 目標**：evaluator `--save-trajectory` 同時產 `.parquet`（含 reward / action / smc 全欄位）與 `.csv`（legacy 精簡欄位）。
**Independent test**：`python -m ppo_training.evaluate ... --save-trajectory` → parquet schema 含 70+ 欄位 + reward invariant；CSV 仍可被舊腳本讀。

### Tests（red）

- [ ] T010 [P] [US2] 在 `tests/unit/ppo_training/test_evaluate_trajectory_parquet.py` 寫測試：用 mini policy + 5-step env fixture 跑 evaluator，驗證 trajectory.parquet 欄位包含 reward 四元、action 四元、smc 五元；reward invariant `total ≈ return − drawdown − cost`（1e-9）；DataFrame 長度 == n_steps + 1
- [ ] T011 [P] [US2] 在 `tests/unit/ppo_training/test_evaluate_csv_compat.py` 寫測試：legacy CSV schema 仍為 `date,nav,log_return,w_*,close_*` 16 欄（FR-005）

### Implementation（green）

- [ ] T012 [US2] 在 `src/ppo_training/evaluate.py` main loop 內新增 action log_prob / entropy 取值（透過 `model.policy.evaluate_actions(obs_tensor, action_tensor)`），存到 per-step list（FR-003）
- [ ] T013 [US2] 在 `src/ppo_training/evaluate.py` main loop 內把 `info["reward_components"]` 拆成 `reward_total / reward_return / reward_drawdown_penalty / reward_cost_penalty` 四欄（FR-002）
- [ ] T014 [US2] 在 `src/ppo_training/evaluate.py` main loop 內把 `info["smc_signals"]` 拆成 5 欄；env 沒有暴露時 fallback 為 0/null（FR-004）
- [ ] T015 [US2] 在 `src/ppo_training/evaluate.py` `--save-trajectory` 路徑寫 `trajectory.parquet`（pyarrow，zstd compression，row group 預設）；CSV 路徑保持原欄位（FR-001 / FR-005）
- [ ] T016 [US2] 跑 T010 / T011 → 應 GREEN；跑 ruff + mypy 通過

---

## Phase 4：User Story 1 — Episode artefact builder + Inference read API（Priority: P1）

**Story 目標**：trajectory.parquet + eval_summary + 6 OHLC parquet → episode_detail.json；005 暴露兩個 read endpoint；前端 Overview 看到真實 OOS 資料。
**Independent test**：`docker compose up` 後 `curl localhost:8080/api/v1/episodes` 回真實 episode；瀏覽器 Overview 頁有真實圖表。

### Artefact builder

#### Tests（red）

- [ ] T020 [P] [US1] 在 `tests/unit/scripts/test_build_episode_artifact_basic.py` 寫測試：給最小 fixture（10 frames × 2 assets）→ builder 產出符合 `EpisodeDetailEnvelope.data` schema 的 dict；reward invariant、weight invariant 全 hold
- [ ] T021 [P] [US1] 在 `tests/contract/episode_artifact/test_artifact_byte_identical.py` 寫測試：跑兩次 builder，assert sha256 相同（憲法 Principle I gate；FR-011）
- [ ] T022 [P] [US1] 在 `tests/unit/scripts/test_build_episode_artifact_smc.py` 寫測試：對 6 檔資產各跑一次 `batch_compute_events`，assert artefact 的 `smcOverlayByAsset` 含 6 keys 且每個 key 有 swings/zigzag/fvgs/obs/breaks（FR-009）

#### Implementation（green）

- [ ] T023 [US1] 在 `scripts/build_episode_artifact.py` 寫 CLI 骨架：argparse `--run-dir / --data-root / --output`；讀 trajectory.parquet + eval_summary.json
- [ ] T024 [US1] 在 `scripts/build_episode_artifact.py` 從 trajectory.parquet 組 trajectoryInline（每 frame 嵌 weights / reward / action / smc / ohlcv / ohlcvByAsset）；OHLC 由 builder 從 `data/raw/<asset>_oos.parquet` join（FR-010）
- [ ] T025 [US1] 在 `scripts/build_episode_artifact.py` 從 byStep 累加產 RewardSeries.cumulative
- [ ] T026 [US1] 在 `scripts/build_episode_artifact.py` 對 6 檔資產各呼叫 `smc_features.batch.batch_compute_events` 產 SMCOverlay（FR-009）
- [ ] T027 [US1] 在 `scripts/build_episode_artifact.py` 用 `EpisodeDetail` pydantic 驗證 payload；違反 → raise + non-zero exit
- [ ] T028 [US1] 在 `scripts/build_episode_artifact.py` 序列化：`json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`；所有 float 先 `round(x, 12)`（R-002 / FR-011）
- [ ] T029 [US1] 在 `scripts/build_episode_artifact.py` 末段印出 sha256 + size，寫到 `--output` 路徑
- [ ] T030 [US1] 跑 T020 / T021 / T022 → 應 GREEN；跑 ruff + mypy 通過

### 005 Inference Service：episodes endpoints

#### Tests（red）

- [ ] T031 [P] [US1] 在 `tests/unit/inference_service/test_episodes_store.py` 寫測試：`EpisodeStore.load_from_path` 能讀合法 artefact；缺檔 → raise；schema 不符 → raise（FR-012）
- [ ] T032 [P] [US1] 在 `tests/integration/inference_service/test_episodes_endpoint.py` 寫測試：FastAPI TestClient + 真實 artefact fixture，`GET /api/v1/episodes` 回 envelope + 1 筆 summary；`GET /api/v1/episodes/{id}` 回 detail；`GET /api/v1/episodes/missing` 回 404（FR-013 / FR-014 / FR-016）
- [ ] T033 [P] [US1] 在 `tests/contract/inference_service/test_episodes_openapi.py` 寫測試：`openapi-spec-validator` 驗 `contracts/openapi-episodes.yaml`；用 `jsonschema` 比對實際 response 與 contract（FR-015）

#### Implementation（green）

- [ ] T034 [US1] 在 `src/inference_service/episodes.py` 新增 `EpisodeStore` 類別：建構子吃 artefact path，load 時用 `EpisodeDetail.model_validate_json` 驗證；提供 `list_summaries() -> list[EpisodeSummary]` 與 `get_detail(id: str) -> EpisodeDetail | None`
- [ ] T035 [US1] 在 `src/inference_service/config.py` 新增 `EPISODE_ARTEFACT_PATH` env（預設 `/app/episode_detail.json`）
- [ ] T036 [US1] 在 `src/inference_service/__main__.py`（或 `app.py` lifespan）新增 startup hook：呼叫 `EpisodeStore.load_from_path(...)` → 存到 `app.state.episode_store`；缺檔 → log FATAL → re-raise（uvicorn 進程非零退出，FR-012 / SC-005）
- [ ] T037 [US1] 在 `src/inference_service/app.py` 新增兩個 route handler：`GET /api/v1/episodes` 與 `GET /api/v1/episodes/{episode_id}`；回傳 `EpisodeListEnvelope` / `EpisodeDetailEnvelope`；找不到回 ApiError 404
- [ ] T038 [US1] 跑 T031 / T032 / T033 → 應 GREEN；跑 ruff + mypy 通過

### 006 Spring Gateway proxy

#### Tests（red）

- [ ] T040 [P] [US1] 在 `services/gateway/src/test/java/com/dayitw/warroom/gateway/controller/EpisodeControllerTest.java` 寫 WireMock contract test：mock 005 → `GET /api/v1/episodes` 回 200 envelope；assert gateway 透傳結構不變
- [ ] T041 [P] [US1] 在同檔案加測試：mock 005 `GET /api/v1/episodes/{id}` 404 → assert gateway 透傳 404 + ErrorEnvelope；timeout → 504
- [ ] T042 [P] [US1] 在 `services/gateway/src/test/.../EpisodeOpenApiTest.java`（若 gateway 有 OpenAPI 驗證骨架）加 contract assertion；無則略過

#### Implementation（green）

- [ ] T043 [US1] 在 `services/gateway/src/main/java/.../dto/EpisodeSummaryDto.java` 用 Java record 定義 summary；對齊 OpenAPI
- [ ] T044 [US1] 在 `services/gateway/src/main/java/.../dto/EpisodeDetailDto.java` 用 Java record + 巢狀 record 定義 detail（trajectoryInline / rewardBreakdown / smcOverlayByAsset）
- [ ] T045 [US1] 在 `services/gateway/src/main/java/.../dto/` 補 envelope record：`EpisodeListEnvelopeDto`、`EpisodeDetailEnvelopeDto`、`ListMetaDto`、`DetailMetaDto`
- [ ] T046 [US1] 在 `services/gateway/src/main/java/.../service/EpisodeClient.java` 用 WebClient 呼叫 005；timeout 5s；錯誤碼透傳
- [ ] T047 [US1] 在 `services/gateway/src/main/java/.../controller/EpisodeController.java` 新增兩個 GET endpoint，pure proxy；ResponseEntity 透傳 status + body
- [ ] T048 [US1] 跑 T040 / T041 → 應 GREEN；`./mvnw -pl services/gateway test` 全綠

---

## Phase 5：User Story 3 — Inference Service Read API 隔離可運行（Priority: P3）

> US3 的核心 endpoint 已在 US1 階段實作；此 phase 專注於 **獨立啟動驗證** 與 fail-fast 行為。

**Story 目標**：不啟動前端、只啟動 redis + 005 + 006 仍能透過 curl 取到合法 episode。
**Independent test**：`docker compose up redis inference-service gateway` → curl 兩個 endpoint 通過 OpenAPI schema 驗證。

### Tests（red）

- [ ] T050 [P] [US3] 在 `tests/integration/inference_service/test_episodes_fail_fast.py` 寫測試：用 lifespan 模式（`with TestClient(app)` / `with lifespan(...)`），設 `EPISODE_ARTEFACT_PATH` 為不存在路徑，預期 lifespan 啟動 raise（SC-005）
- [ ] T051 [P] [US3] 在 `tests/integration/inference_service/test_episodes_404_format.py` 寫測試：`GET /api/v1/episodes/url%2Funsafe` 與 `GET /api/v1/episodes/does-not-exist` 都回 404 + ApiError schema（FR-016）

### Implementation（green）

- [ ] T052 [US3] 確認 T036 的 fail-fast：lifespan 內不要 swallow exception；run T050 → GREEN
- [ ] T053 [US3] 確認 episode_id path validation（pattern `^[A-Za-z0-9_\-:.]+$`）：違反 → 404 而非 500；run T051 → GREEN

---

## Phase 6：Image build + e2e

- [ ] T060 在 `infra/Dockerfile.inference` 加 `COPY infra/inference/artefact/episode_detail.json /app/episode_detail.json`；env `EPISODE_ARTEFACT_PATH=/app/episode_detail.json`
- [ ] T061 在 `infra/docker-compose.gateway.yml` 確認 inference service 注入 `EPISODE_ARTEFACT_PATH` env（如已是 image default 則跳）
- [ ] T062 在 `.gitignore` 加 `infra/inference/artefact/episode_detail.json`（不污染 git history）；同時新建空的 `infra/inference/artefact/.gitkeep`
- [ ] T063 [P] 跑 quickstart.md 步驟 1 → 步驟 4，確認 `docker compose up --build` 在乾淨機器啟動成功且 005 startup log 顯示 EpisodeStore 載入訊息

---

## Phase 7：Frontend mapper + Overview wiring

- [ ] T070 [P] 在 `apps/warroom/src/api/episodes.ts` 確認 `toEpisodeSummary` / `toEpisodeDetail` 對齊 OpenAPI envelope；如缺則新增；用 zod `.strict()`
- [ ] T071 [P] 在 `apps/warroom/src/api/__tests__/episodes.test.ts` 寫 vitest：完整 payload → 通過；缺欄位 → throw `ApiError`（FR-019）
- [ ] T072 在 `apps/warroom/src/pages/OverviewPage.tsx` 移除 mock fixture fallback（如有）；改成 `useQuery` error → 明確錯誤狀態（FR-020）
- [ ] T073 [P] 在 `apps/warroom/src` 跑 `pnpm -C apps/warroom test` 全綠
- [ ] T074 [P] 在 `apps/warroom/src` 跑 `pnpm -C apps/warroom build` 通過（type check）

---

## Phase 8：Polish

- [ ] T080 [P] 跑 `ruff check .` 全綠
- [ ] T081 [P] 跑 `mypy src/inference_service src/ppo_training scripts/build_episode_artifact.py` 全綠
- [ ] T082 [P] 跑 `pytest tests/ -q` 三 marker 全綠；新增程式碼 coverage ≥ 80%
- [ ] T083 [P] 跑 `./mvnw -pl services/gateway test` 全綠
- [ ] T084 跑 quickstart.md 步驟 3（byte-identical sha256 比對）→ 必須 PASS（憲法 Principle I gate）
- [ ] T085 跑 quickstart.md 步驟 5–6 → curl 兩 endpoint + 開瀏覽器 Overview 頁，所有面板顯示真實 OOS 數據（SC-001 / SC-002 / SC-003）
- [ ] T086 更新 CLAUDE.md `<!-- SPECKIT START --> ... <!-- SPECKIT END -->` 區塊：phase 標 `/speckit.implement complete`

---

## Dependencies

- **T001 → 全部**（baseline 紅就停）
- **T004 阻塞 T031, T034, T037, T020, T027**（schema 是 foundation）
- **Phase 3（US2）阻塞 Phase 4 builder（T023+）**（trajectory.parquet 是 builder input）
- **Phase 4 builder（T023~T030）阻塞 Phase 4 005 endpoints（T034+）的 integration test fixture 生成**
- **Phase 4 005（T034~T038）阻塞 Phase 4 006（T046+）的 WireMock contract**（拿 005 真實 response 當 fixture）
- **Phase 4 完成 阻塞 Phase 5（US3 是 US1 的隔離驗證）**
- **Phase 6 image 阻塞 Phase 7 e2e（T085）**
- **Phase 5/6/7 都做完才能跑 Phase 8 polish**

## Parallelization

- T002, T003 可並行（pyproject vs package.json）
- T010, T011 可並行（不同測試檔）
- T020, T021, T022 可並行（不同測試檔）
- T031, T032, T033 可並行
- T040, T041, T042 可並行（同類 Java test）
- T050, T051 可並行
- T070, T071, T073, T074 可並行
- T080, T081, T082, T083 可並行（不同 lint / test 命令）

## Acceptance criteria mapping

| Task | FR | SC | Contract invariant |
|---|---|---|---|
| T010~T015 | FR-001~005 | — | trajectory.parquet schema |
| T020~T030 | FR-007~011 | SC-004 | EpisodeDetail schema + sha256 byte-identical |
| T031~T038 | FR-012~016 | SC-002 / SC-003 / SC-005 | OpenAPI episodes |
| T040~T048 | FR-017 / FR-018 | SC-006 | OpenAPI episodes |
| T070~T074 | FR-019 / FR-020 | SC-001 / SC-007 | EpisodeDetailViewModel zod |

## MVP suggested order

最小可展示 demo：T001 → T004~T005 → T010~T016（US2）→ T020~T030（builder）→ T031~T038（005 endpoints）→ T060~T063（image）→ T070~T072（前端 wiring）→ quickstart.md e2e 確認。
US3（T050~T053）與 polish（Phase 8）可在 demo 完成後補強。
