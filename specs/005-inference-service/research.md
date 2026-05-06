# Research: 推理服務（005-inference-service）

> **⚠️ SUPERSEDED — 2026-05-06**
> 本 research 紀錄對應舊版 spec 的技術決策（FastAPI 為主、Prometheus、multi-policy 管理）。
> spec.md 已於 2026-05-06 重寫為 C-lite，新的決策（Redis pub/sub vs Kafka、APScheduler、docker-compose → Zeabur）已記錄在 memory `project_warroom_architecture_decisions.md`。
> 重新跑 `/speckit.plan` 時會重新生成本檔的 Phase 0 區塊。

Phase 0 決策紀錄。每項以「Decision / Rationale / Alternatives considered」格式呈現。

## R1: HTTP framework 選型 — FastAPI

**Decision**: 採用 FastAPI 0.110+ 配 uvicorn 0.29+。

**Rationale**:

1. **OpenAPI 3.1 自動生成**：直接滿足 FR-015、FR-017，不需手寫 OpenAPI yaml。
2. **Pydantic 2.x 整合**：request/response schema 在 Python type 系統內表達，與 stable-baselines3 / numpy 生態相容性好。
3. **Async-native**：sse-starlette + uvicorn workers 可支援 100 並發 + SSE streaming（FR-006、SC-006）。
4. **生態成熟**：openapi-spec-validator、httpx、pytest-asyncio 一條龍。
5. **與 stable-baselines3 同 Python 進程**：避免跨進程序列化 policy（zip 載入 ~5 MB，每次 RPC 太重）。

**Alternatives considered**:

- **Flask + flasgger**：OpenAPI 為手寫附加層、async 不原生、效能 < FastAPI。Reject。
- **gRPC**：跨語言型別嚴格但 (a) 需額外 protobuf compile 流程、(b) 006 Java 端 stub 生成複雜度反而高、(c) 瀏覽器端（007）無原生支援需 grpc-web。Reject — 採 OpenAPI 介接 simpler。
- **Tornado / aiohttp**：async OK 但 OpenAPI 整合需額外套件、生態不如 FastAPI。Reject。

## R2: Policy 載入策略 — 啟動時 default + 動態 load

**Decision**: 服務啟動時從環境變數 `INFERENCE_DEFAULT_POLICY_PATH` 載入一個 default policy；其餘 policy 透過 `POST /v1/policies/load` 動態載入。所有 policy 常駐記憶體（dict[policy_id, PolicyHandle]）。

**Rationale**:

1. **K8s readiness probe 對齊**：default 載入完成才 `/readyz` 200，符合標準 K8s pattern。
2. **多 policy 切換是 P2 需求**（FR-007~FR-009），動態 API 滿足論文 demo 場景。
3. **記憶體成本可控**：每 policy ~5 MB（PPO 小網路），10 個 policy < 100 MB；遠低於現代容器 RAM limit（512 MB ~ 4 GB）。
4. **無 LRU eviction**：簡化邏輯；超過 10 個由運維手動 DELETE。

**Alternatives considered**:

- **Lazy load（首次推理才 load）**：首次延遲不可控、違反 SC-008（5 秒內 ready）。Reject。
- **Per-request load**：每次推理重讀 zip → I/O 不可承受、違反 SC-001 latency budget。Reject。
- **共享記憶體 / mmap policy**：sb3 PPO `.zip` 為 pickle 不適合 mmap。Reject。

## R3: Episode API 與 003 跨層 byte-identical 保證

**Decision**: `POST /v1/episode/run` 內部 `from portfolio_env import PortfolioEnv; env = PortfolioEnv(...); env.reset(seed=req.seed); ...` 直接 import 003 package，逐步呼叫 `policy.predict(obs, deterministic=True)` + `env.step(action)`，收集 info dict。回傳前以 003 之 `info_to_json_safe()` 轉 JSON-safe。

**Rationale**:

1. **單一資料路徑**：env+policy 計算 100% 與直接 import 一致，零隔閡 → 自動滿足 SC-004、FR-005。
2. **避免重實作**：reward 計算、SMC 訊號、weight clipping 全部仰賴 003，不在本 feature 範圍。
3. **info schema 統一**：序列化用 003 之 `info-schema.json`，避免 schema drift（FR-016）。

**Alternatives considered**:

- **重新實作 episode loop**：違反 DRY、必然 byte-divergent。Reject。
- **跨進程呼叫 003 worker**：增加序列化開銷與一致性風險。Reject。

**Key constraint**：本服務必依賴 003 package（`pip install -e ../portfolio_env`），plan 結構假設 003 為 importable（與 003 計畫一致）。

## R4: API 介接協定 — REST/JSON over HTTP（vs. gRPC）

**Decision**: REST/JSON over HTTP 1.1（FastAPI 預設），OpenAPI 3.1 為主契約。

**Rationale**:

1. **006 Java client 生成簡單**：openapi-generator-cli java 產出 stub 是 spring-cloud 慣例。
2. **007 React 端生成簡單**：openapi-typescript / orval 產 TS client。
3. **瀏覽器原生支援**：未來若 007 直連推理服務（不經 Gateway）可行。
4. **debug 友好**：curl / postman / browser 直接驗證。
5. **效能 50ms p99 budget 充足**：FastAPI + orjson serialize 對 ~1KB payload 序列化 < 1ms，網路 1ms（內網），policy.predict 5-10ms → 餘裕大。

**Alternatives considered**:

- **gRPC**：見 R1 alternatives；型別嚴格但生態複雜度過高、瀏覽器需 envoy proxy。Reject。
- **MessagePack / CBOR**：payload 縮小但失去 debug 友好性、JSON 1KB 不是瓶頸。Reject。

## R5: SSE vs WebSocket vs HTTP chunked — episode streaming

**Decision**: 採用 Server-Sent Events (SSE) via `sse-starlette`，端點 `POST /v1/episode/stream`。

**Rationale**:

1. **單向推送（server → client）即足**：episode 推理只需 server 推送進度，不需 client 雙向訊息。
2. **HTTP/1.1 原生**：不需 ws upgrade、proxy / Gateway 透傳簡單。
3. **瀏覽器原生 EventSource API**：007 React 接收方便。
4. **連線中斷可恢復**：SSE `Last-Event-ID` 標準允許 client 斷線 reconnect 續接（雖非本 feature 必須）。

**Alternatives considered**:

- **WebSocket**：雙向過剩、Gateway 透傳複雜、proxy 兼容性差。Reject。
- **HTTP chunked transfer encoding（無 SSE 框架）**：可行但 client 需手動解析、缺少 event id/retry 標準。Reject。
- **Long polling**：高延遲、不適合 episode 動畫播放。Reject。

## R6: Prometheus metrics 暴露策略

**Decision**: `prometheus-client` library，`GET /metrics` 端點，採 pull 模式（被 Prometheus server scrape）。Histogram bucket 採預設 + 自訂（0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0 秒）覆蓋 50ms p99 budget。

**Rationale**:

1. **K8s 標準對接**：Prometheus Operator + ServiceMonitor 自動 scrape。
2. **Pull 模式無狀態**：服務 down 不會丟 metric、Prometheus 端統一保留策略。
3. **Histogram 對 latency budget 必須**：p99 計算需要 bucket，Counter 不夠。

**Alternatives considered**:

- **Push to Pushgateway**：適合 batch job 不適合長駐 service。Reject。
- **OpenTelemetry**：spec 更通用但生態尚未完全替代 Prometheus、增加維運負擔。Reject（未來可加）。
- **Statsd**：UDP 不可靠、缺 histogram。Reject。

## R7: 結構化 log — JSON to stdout

**Decision**: stdlib `logging` + 自訂 JSONFormatter 輸出至 stdout；level=INFO 預設、可由 `LOG_LEVEL` env var 覆寫。Stack trace 寫 stderr、不入 JSON log。

**Rationale**:

1. **K8s log 收集**：fluentd / promtail / vector 統一抓 stdout。
2. **JSON 易解析**：Loki / Elasticsearch / Datadog 可直接 index 欄位（inference_id、policy_id、latency_ms）。
3. **stack trace 走 stderr**：避免污染 INFO log、運維可分流；同時 FR-014 要求「response body 不洩漏 stack trace」、log 系統內保留供事後分析。

**Alternatives considered**:

- **structlog**：更彈性但對本 feature 規模 overengineering。Reject（未來可換）。
- **stdout 文字 + 後端解析**：失去結構化 query 能力。Reject。

## R8: OpenAPI yaml 寫出策略

**Decision**: 服務啟動時 FastAPI 產生 OpenAPI 3.1 dict；CI step（在 build pipeline 內）執行 `python -m inference_service dump-openapi --output contracts/openapi.yaml` 將最新 schema 寫出並 git diff 檢查；若有差異 CI fail，要求開發者重新 commit。

**Rationale**:

1. **契約先行**：006 Java stub 從 commit 中的 yaml 生成，不依賴 service runtime。
2. **drift detection**：CI gate 防止 code 與 yaml 不一致。
3. **無需手寫 yaml**：FastAPI 自動產生為 source of truth。

**Alternatives considered**:

- **動態 fetch from `/openapi.json`**：006 build 需要服務先啟動、CI 流程複雜化、跨 repo 依賴 brittle。Reject。
- **手寫 yaml**：違反 DRY、易與 code drift。Reject。

## R9: Concurrency model — uvicorn workers + async handler

**Decision**: uvicorn `--workers 1 --loop uvloop`（單 worker，async event loop）；所有 handler 為 `async def`；policy.predict 為同步 CPU 計算，包在 `await asyncio.to_thread(policy.predict, ...)` 內避免阻塞 event loop。

**Rationale**:

1. **單 worker 共享 policy registry**：避免 multi-process 各自載入 policy（記憶體 × N）。
2. **async event loop**：100 並發連線僅靠單線程處理 I/O，CPU 密集部分（policy.predict）扔 thread pool。
3. **uvloop 加速**：較預設 asyncio loop 快 2-4 倍。

**Alternatives considered**:

- **多 worker（gunicorn + uvicorn worker class）**：每 worker 獨立載入 policy → 記憶體 × N、policy registry 分裂。Reject 為本 feature 範圍。
- **sync flask + gunicorn**：阻塞 I/O 不適合 SSE。Reject。
- **僅同步 FastAPI**：FastAPI 仍可跑 sync handler 但 SSE 必須 async。混用反而複雜。Reject。

## R10: Error response 一致性

**Decision**: 所有錯誤回應走統一 schema：

```json
{
  "error": {
    "code": "OBSERVATION_DIM_MISMATCH",
    "message": "Expected dim 63, got 33",
    "error_id": "uuid-v4",
    "details": { "expected": 63, "got": 33 }
  }
}
```

HTTP status code 配合語意（400 client error、404 policy not found、409 policy_id 重複、500 internal、503 not ready）。錯誤碼字典寫 `contracts/error-codes.md`。

**Rationale**:

1. **006 Java client mapping 簡單**：固定 schema → exception class 一一對應。
2. **error_id 用於追蹤**：log 內含同 id、運維可串接。
3. **details object 開放**：細節可擴充而不破壞 schema。

**Alternatives considered**:

- **RFC 7807 Problem Details**：標準但欄位多餘（type URI、instance）；本 feature 內網不需。Reject。
- **散落的 error format**：每端點各自定義 → 客戶端 boilerplate 多。Reject。
