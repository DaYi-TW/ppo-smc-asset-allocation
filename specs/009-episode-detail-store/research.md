# Research: PPO Episode Detail Store

**Feature**: 009-episode-detail-store
**Date**: 2026-05-07

## R-001 Trajectory persistence 格式

**Decision**: 主檔 Parquet（zstd compression、row-group 預設），同時保留 legacy CSV。

**Rationale**:
- pandas / pyarrow 直讀；schema 自帶（dtype、column names），artefact builder 不需另外帶 schema 檔。
- 包含巢狀欄位（reward 四元、action 四元、smc 五元）時 parquet 用 struct dtype 即可；CSV 要 flatten 才行。
- legacy CSV 維持精簡欄位（date / nav / log_return / weights / closes），保證既有 Colab notebook 不破。

**Alternatives**:
- JSONL：人類可讀，但 329 frames × 100 fields 體積過大、讀取慢、no schema enforcement。
- 直接 in-memory pass：違反 service decoupling（artefact builder 需獨立可跑）。

**載荷估計**：329 frames × ≈ 80 numeric fields ≈ 1.6 MB raw → zstd ≈ 0.3 MB。

## R-002 Episode artefact 序列化策略

**Decision**: 單一 JSON 檔，序列化參數 `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`，所有 float 先 `round(x, 12)`。

**Rationale**:
- byte-identical 要求（憲法 Principle I）：`sort_keys` 消除 dict 順序非確定性；`separators` 移除空白；`allow_nan=False` 強制呼叫端處理 NaN（NaN 在 JSON 規範外）。
- 5 MB JSON 對 image build 不構成壓力（Docker layer caching 仍有效，artefact 為單一 layer）。
- 人類可讀，方便 debug。
- 與前端 zod schema 對齊；無需引入 MessagePack 等二進位格式的客戶端 codec。

**Alternatives**:
- MessagePack：體積較小但前端需新增 codec；增加複雜度，benefit 不夠。
- 多 JSON 檔（拆 trajectory / smc / overview）：拆檔 → 5 個檔案 → 增加載入順序與失敗處理複雜度，且 byte-identical 要 hash 5 次。

**Float 取整**：`round(x, 12)` 在 NAV / weight / reward 量級下保留全部有效位（NAV 通常 1e-1 量級，weight 0~1，reward 1e-3 量級），不丟資訊。

## R-003 EpisodeStore 載入策略

**Decision**: Eager load on FastAPI lifespan startup；artefact 缺檔則 raise → uvicorn fail fast。

**Rationale**:
- FR-012 / SC-005：缺檔須 30s 內以非零 exit code 終止；lazy load 會在第一個 request 才報錯，違反 spec。
- 5 MB JSON parse 在 Python 約 50–100 ms，對 startup 影響可忽略。
- 載入後存到 `app.state.episode_store`，每次 request 為純 dict lookup → < 1 ms。

**Alternatives**:
- Lazy load：違反 spec（fail fast）。
- 走 redis：增加 redis 對 episode 的依賴；但 episode 是 build-time artefact，無動態 publish 需求。

## R-004 OpenAPI envelope 結構

**Decision**:
- List endpoint：`{ items: EpisodeSummaryDto[], meta: { count: number, generated_at: string } }`
- Detail endpoint：`{ data: EpisodeDetailDto, meta: { generated_at: string } }`
- Error：複用既有 `ErrorResponse`（005）/ `ErrorResponseDto`（006）

**Rationale**:
- 對齊既有 005 / 006 endpoint 的 envelope 風格（搜 `services/gateway/src/main/java/.../dto/` 既有 dto 命名）。
- `meta` 留擴充欄位（pagination、cursor）但 MVP 只塞 `count` + `generated_at`。
- 前端既有 envelope mapper（`apps/warroom/src/api/`）已假設此結構；無需動 mapper interface。

## R-005 Action vector 取值方法

**Decision**: 使用 `model.policy.evaluate_actions(obs_tensor, action_tensor)`，回傳 `(values, log_prob, entropy)`；raw 直接從 `model.predict(obs, deterministic=True)` 取（pre-softmax wrapper 那層）。

**Rationale**:
- sb3 PPO `policy` API 已標準提供；無需自定 hook。
- raw 從 wrapper 之前取（`_SoftmaxActionWrapper.action()` 的 input）；normalized = wrapper output。

**Alternatives**:
- `policy.get_distribution(obs).log_prob(action)`：等價，但需手動 reshape；fallback only。
- 自己重算 entropy：違反 single source of truth。

**Spike 結果**：在 evaluator 的 main loop 中，加 4 行從 model.policy 取 log_prob / entropy 即可；不影響原 deterministic semantic（sb3 policy.evaluate_actions 不改變 RNG state）。

## R-006 SMC signals 來源

**Decision**: 直接讀 `info["smc_signals"]`（PortfolioEnv 在 step return info 中已暴露）；若某 frame 缺欄位則由 artefact builder 後處理時用 008 SMC engine 補算（per-frame 取「至最近 swing 的距離」）。

**Rationale**:
- env 已是 single source of truth；artefact builder 不應重算邏輯。
- 後處理 fallback 僅作為防禦；正常路徑下 env 提供完整五元。

**驗證**：Phase 1 unit test 跑迷你 episode 後 assert 每 frame 的 `info["smc_signals"]` 存在 5 個 key。

## R-007 SMC overlay per asset 計算

**Decision**: artefact builder 對 6 檔資產各跑一次 `smc_features.batch.batch_compute_events(ohlcv_df, ...)`，回傳 SMCOverlay（swings / zigzag / fvgs / obs / breaks）。

**Rationale**:
- 008-smc-engine-v2 已有 batch API；artefact builder 直接 import。
- 確保前後端用同一 SMC 規則（FR-009）。

**性能**：6 assets × 329 days × O(N) 計算 ≈ 數百 ms。在 builder 一次性執行，不影響 runtime。

## R-008 byte-identical reproducibility 驗證

**Decision**: 新 contract test：`tests/contract/episode_artifact/test_artifact_byte_identical.py`，跑兩次 `build_episode_artifact.py`，比對 sha256 必須相同。

**Rationale**:
- 憲法 Principle I 驗收標準的具體實作 gate。
- 任何把非確定性引入 artefact（如 timestamp、random suffix）的 PR 都會在這個 test 紅。

**注意**：test 不能依賴真實 evaluator output（太慢 + 需要 policy.zip）；改用最小 fixture（10 frames × 2 assets），驗證序列化邏輯本身是確定性的即可。實際 OOS run 的 byte-identical 留給 quickstart.md 手動驗證。

## R-009 Image build 對 artefact 的處理

**Decision**: `infra/Dockerfile.inference` 加 `COPY infra/inference/artefact/episode_detail.json /app/episode_detail.json`；artefact 由 build_episode_artifact.py 在 build 之前生成並複製到該位置；不打進 git（large file），但補在 `.gitignore` allow-list 或由 CI build step 生成。

**Rationale**:
- 不污染 git history（5 MB binary）。
- 開發者本地 build 流程：`python -m ppo_training.evaluate ...` → `python scripts/build_episode_artifact.py --output infra/inference/artefact/episode_detail.json` → `docker compose build inference`。
- quickstart.md 文件化整個流程。

**Alternatives**:
- 走 git LFS：依賴 LFS infra；MVP 不引入。
- runtime 從 redis / S3 拉：違反 spec out-of-scope（無動態存儲）。

## R-010 frontend mapper 嚴格模式

**Decision**: zod schema 用 `.strict()`，未知欄位 → throw；`toEpisodeSummary` / `toEpisodeDetail` 在收到不符 schema 的 payload 時拋 `ApiError`，由 React Query error boundary 接住。

**Rationale**:
- 防止 schema 漂移無聲蔓延（spec FR-019）。
- 開發階段早期暴露 API 契約 bug。

**注意**：MVP 階段前端 viewmodel 已定型；本 feature 只需確認 mapper 對齊，不改 viewmodel interface。
