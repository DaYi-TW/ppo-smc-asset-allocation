# Research: 推理服務（005-inference-service）— C-lite 版

**Last Major Revision**: 2026-05-06（重寫對齊 C-lite 範圍；舊版決策附 §11 Legacy Notes）

Phase 0 決策紀錄。每項以「Decision / Rationale / Alternatives considered」格式呈現。所有決策對齊 spec.md（2026-05-06 重寫版）與 memory `project_warroom_architecture_decisions.md`。

---

## R1: HTTP framework — FastAPI

**Decision**: 採用 FastAPI 0.115+ 配 uvicorn 0.32+。

**Rationale**:
- Pydantic 2.x 整合直接 → `PredictionPayload` 雙向（serialize / validate）
- 自動 OpenAPI 3.1 → `GET /openapi.json`，前端 / Spring 直接吃
- async-native → 與 APScheduler `AsyncIOScheduler` + redis async client 同 event loop
- 業界事實標準 → CI / Zeabur / Docker recipe 充足

**Alternatives considered**:
- Flask + Flask-RESTX：sync-first，要併入 scheduler 就要多開 thread / process，複雜度高
- Starlette 裸用：要自己寫 schema 驗證、OpenAPI 產出、route decorator，違反 YAGNI
- aiohttp：成熟但社群比 FastAPI 小，OpenAPI 整合差

---

## R2: Scheduler — APScheduler with pytz ET

**Decision**: 採用 `apscheduler ~= 3.10` 的 `AsyncIOScheduler` + `CronTrigger.from_crontab("30 16 * * MON-FRI", timezone=pytz.timezone("America/New_York"))`。

**Rationale**:
- AsyncIO native，與 FastAPI 同 process / 同 loop
- pytz timezone 自動處理 DST（不像 server local time 在 3/9、11/2 會錯）
- `MON-FRI` 限制只在交易日跑（週末 yfinance 無新資料）
- 內建 misfire_grace_time 機制：服務重啟後若錯過 trigger，可決定要跑或跳過（設 5 分鐘 grace）

**Alternatives considered**:
- `schedule` library：sync-only，要包 thread；無 timezone 支援
- `croniter` + 自寫 loop：DST 邏輯要自己處理，容易錯
- 外部 cron（cron daemon / GitHub Actions cron）：失去「同 process」的 mutex 共享，要靠 Redis lock 實現互斥，複雜度高
- Linux systemd timer：不能跨平台（Zeabur 用 container runtime 不一定能跑 systemd）

**Risk note**: APScheduler 3.x 與 4.x 不相容（API 重設計），鎖在 3.10 至 MVP 上線後再評估升級。

---

## R3: 訊息層 — Redis pub/sub（不上 Kafka）

**Decision**: 採用 `redis[hiredis] ~= 5.0` async client。
- Channel: `predictions:latest`（新事件廣播）
- Key: `predictions:latest`（最新一筆 cache，TTL 7 天）

**Rationale**:
- 業務量：1 天 1~5 個 event、1 個訂閱者（006 Spring Gateway）→ 完全不需要 Kafka 的 partition / consumer group / 持久化保證
- Redis 部署簡單：本機 docker-compose `redis:7-alpine`、Zeabur 有 managed Redis add-on，免維運
- pub/sub + GET 雙模式同一個 Redis instance 搞定（broadcast 給活著的訂閱者，cache 給後到訂閱者初始化）
- hiredis 加速序列化（純 redis-py 慢約 3x）

**Alternatives considered**:
- Apache Kafka：對單人研究專案過度工程；ZooKeeper / KRaft 維運負擔；Zeabur 不友善
- RabbitMQ：仍比 Redis 重；多了 routing key / exchange 概念，本場景無需
- HTTP webhook（python-infer 直接 POST 給 Spring Gateway）：要寫重試 / 回壓 / 訂閱者管理，不如靠 Redis 解耦
- Redis Streams（XADD / XREAD）：適合需要回放 / consumer group，本場景的 "pub/sub + last-known cache" 用 PUB/SUB + SET TTL 即可，不需要 Streams 的複雜度

**Constitution Variance**: 憲法 §IV 原文要求「Kafka 訊息」，本決策已記錄 Variance（見 plan.md §Constitution Variance），由 user 2026-05-06 明示同意。

---

## R4: Inference handler 共用設計 — 單一 async function + asyncio.Lock

**Decision**: 在 `handler.py` 定義 `async def run_inference(triggered_by: str) -> PredictionPayload`，scheduled 與 manual 兩條入口都呼叫此函式。互斥用 module-level `asyncio.Lock`。

**Rationale**:
- 共用實作 = byte-identical 結果保證（SC-007 / Gate I-1）
- `asyncio.Lock` 在同一 event loop 天然 FIFO 排隊，不需要額外 queue
- async function 讓 FastAPI endpoint 可以 `await`，scheduler callback 也可以 `await`
- 不用 `threading.Lock` — 因為 FastAPI / APScheduler 都 async，混 thread 反而要 GIL + thread pool，沒好處

**Alternatives considered**:
- 兩條獨立 inference path（複製貼上 predict.py 邏輯）：違反 DRY、會漂移
- `multiprocessing.Lock`：跨 process，但本服務 single-process，過度
- Redis-based distributed lock（Redlock）：未來上 multi-replica 才需要；MVP 1-replica 用 in-process lock 即可
- queue-based serialization（`asyncio.Queue` + worker task）：更靈活但本場景只是純 mutex，YAGNI

**Risk note**: 第二個 await 會等到第一個跑完（最多 90 秒），manual trigger 可能感受卡頓。Acceptance scenario 已涵蓋（spec User Story 2 §Acceptance #2）。

---

## R5: Policy 載入策略 — eager load on startup（不動態 reload）

**Decision**: 服務啟動時讀 `POLICY_PATH` env var、立即 `PPO.load()`，整個 process 生命週期持有同一個 model 實例。policy 換版要重 build image + 重啟 container。

**Rationale**:
- MVP 階段不需要熱換 policy（論文 demo 用一個固定 policy）
- eager load 避免「第一個請求慢」的冷啟動問題
- container 化原則：image 是 immutable artifact，policy 屬於 image 的一部分
- Zeabur 上重啟 container ~10 秒，可接受

**Alternatives considered**:
- Lazy load：第一次 inference 才載入，但會讓 cold start 後的第一個 manual trigger 慢 ~5 秒
- 動態 reload endpoint（`POST /policy/reload`）：增加 attack surface + 多狀態管理；MVP 不需要
- Mount policy as volume：違反 image immutable；本機 docker-compose 可以、Zeabur 不友善

---

## R6: Data 載入策略 — copy data/raw into image

**Decision**: Dockerfile build 時把 `data/raw/*.parquet` 全部 copy 進 image。執行期不掛 volume、不下載。

**Rationale**:
- 8 個 Parquet 檔總計 < 50 MB，image 不會爆
- 避免執行期「下載資料 → 計算 hash → 比對」的延遲（002 既有 hash gate）
- 與 policy 一樣走 immutable artifact 路線
- 之後資料更新流程：`ppo-smc-data update` → 重 build image → 重新 deploy

**Alternatives considered**:
- Volume mount：違反 immutable；cold start 要重新驗證 hash gate
- 執行期下載：yfinance / FRED 限速，不適合 production cold start
- Sidecar 容器負責 data sync：增加架構複雜度

**Risk note**: 每次資料更新要 rebuild image（~30-60s），cron 化整個流程屬未來自動化（GitHub Actions on schedule + Zeabur webhook）。

---

## R7: Prediction schema 對齊 — 共用 Pydantic model

**Decision**: 在 `src/inference_service/schemas.py` 定義 `PredictionPayload` Pydantic model，欄位 1:1 對齊 `predict.py` 既有 JSON schema + 新增 `triggered_by: Literal["scheduled","manual"]` + `inference_id: UUID`。Contract test 驗證 service 輸出 == predict.py 輸出（除了新加欄位）。

**Rationale**:
- 前端 / 006 Gateway 不需改 parser（schema 99% 相容）
- Pydantic 幫忙做型別驗證 + JSON serialize（orjson backend）
- 加 `triggered_by` 讓訂閱者區分自動 vs 手動
- 加 `inference_id` 給 log / trace 用

**Alternatives considered**:
- 完全沿用 `predict.py` 的 dict（不定義 Pydantic）：失去型別檢查、OpenAPI 產出會空
- 重新設計 schema：違反「前端不用改」承諾（FR-006）
- 把 schema 抽到 `src/ppo_training/schemas.py` 共用：predict.py 是 CLI 工具，目前不依賴 Pydantic，加進去要改既有測試

**Risk note**: predict.py 改 schema 時、本 service 要同步追；Phase 7 contract test 自動 catch（diff 失敗）。

---

## R8: Test 策略 — fakeredis（unit）+ testcontainers（integration）

**Decision**:
- Unit test 用 `fakeredis ~= 2.26`（內存 Redis、快、隔離）
- Integration test 用 `testcontainers[redis] ~= 4.8` 起真 `redis:7-alpine` container（驗證 pub/sub timing、TTL 行為）
- Contract test 直接 import `predict.py` 跑一次 + service `/infer/run` 一次、JSON diff

**Rationale**:
- fakeredis 跑 ms 級、CI 不需要 docker-in-docker
- testcontainers 對「pub/sub 真的會通知訂閱者嗎」這種 timing 行為唯一可信驗證方式
- contract test 是本 feature 的核心 invariant（schema 對齊），不能 mock

**Alternatives considered**:
- 全部用真 Redis：CI 慢、setup 複雜
- 全部用 fakeredis：pub/sub timing 不真實
- 只做 unit、跳 integration：跨 process / 跨 timing 的 bug 抓不到（DST、publish 失敗 retry）

---

## R9: Cold start 預算

**Decision**: container cold start ≤ 60 秒（SC-008）。預算分配：
- Image pull / start：~5 秒（slim image + Zeabur infra）
- Python 啟動 + import：~3 秒
- Policy load (PPO.load)：~5-10 秒
- PortfolioEnv construct（不跑 episode、只 init）：~3 秒
- Scheduler 註冊：< 1 秒
- FastAPI bind port：< 1 秒
- 緩衝：剩 ~30 秒

**Rationale**:
- Zeabur health probe 預設 30 秒檢查一次，設 cold start ≤ 60s 給足兩個 retry 視窗
- 第一個 inference latency 不算 cold start（屬 SC-001 90 秒預算）

**Alternatives considered**:
- 把 PPO.load 放第一個 inference 內：cold start 快但首次 inference 變慢，違反「健檢回 200 後就應該能服務」原則
- 起動時 warm up env 跑一次 inference：cold start 變 90 秒，超預算

---

## R10: Logging — 結構化 JSON to stdout

**Decision**: 用 stdlib `logging` + `python-json-logger`（或自寫 formatter）輸出 JSON 一行一筆到 stdout；error trace 走 stderr。

**Rationale**:
- Zeabur / docker-compose / Loki / CloudWatch 全部吃 stdout JSON 格式
- 結構化 log 方便後續 query（`grep '"event":"scheduled_inference_failed"'`）
- 不寫 log 檔（容器化原則：log 由 platform 收集）

**Alternatives considered**:
- structlog：功能多但本 feature 場景簡單，stdlib 夠用
- loguru：好用但又一個 dependency；本專案盡量壓 dependency
- 寫 file log：違反 12-factor，volume 管理麻煩

---

## R11: Legacy Notes（舊版本決策回溯）

舊版 spec（2026-04-29）的決策保留參考：

- 舊 R1: FastAPI + Prometheus client + `/metrics` exposition format → C-lite 移除 `/metrics`，logging 走 stdout 即可
- 舊 R3: 多 policy 動態 dict[policy_id, PolicyHandle] → C-lite 採單一 default policy
- 舊 R5: SSE for episode replay → C-lite 移除 episode replay endpoint（屬 future）
- 舊 R7: 50ms p99 latency budget → C-lite 放寬到 90 秒（涵蓋 env warmup）

舊內容保留於 git history（commit `77f3450` 之前），需要時可 `git show 77f3450:specs/005-inference-service/research.md` 回查。
