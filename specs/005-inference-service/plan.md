# Implementation Plan: 推理服務（Inference Service）

**Branch**: `005-inference-service` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-inference-service/spec.md`

## Summary

對外提供 PPO 推理 HTTP API（FastAPI + uvicorn），載入 004 訓練產出之 `final_policy.zip`，暴露 `/v1/infer`、`/v1/episode/run`、`/v1/episode/stream`（SSE）、`/v1/policies` 管理端點與 `/healthz`、`/readyz`、`/metrics` 三個維運端點。技術核心：(a) FastAPI 自動產出 OpenAPI 3.1 spec → commit 入 repo 供 006 Java client stub 生成；(b) policy 物件以 dict[policy_id, PolicyHandle] 常駐記憶體、stateless service；(c) episode 推理路徑直接 import 003 PortfolioEnv，保證跨層 byte-identical（FR-005、SC-004）；(d) Prometheus metrics + 結構化 JSON log 對接 K8s。

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: fastapi ~= 0.110、uvicorn[standard] ~= 0.29、stable-baselines3 ~= 2.3、pydantic ~= 2.6、prometheus-client ~= 0.20、sse-starlette ~= 2.0、PyYAML、orjson（高速 JSON serialize）。Dev: pytest、pytest-asyncio、httpx（async test client）、openapi-spec-validator。
**Storage**: Stateless；policy zip 由本地 fs 載入（K8s PVC 掛載或共享 volume），無 DB。
**Testing**: pytest + httpx async client；contract tests 對 OpenAPI schema、integration tests 對 003 + 004 byte-identical 檢查。覆蓋率 ≥ 85%（SC-007）。
**Target Platform**: Linux 容器（K8s）、本地 macOS/Windows 開發；Python 3.11+ 跨平台。
**Project Type**: Single project（純後端服務，無前端）。`src/inference_service/` package。
**Performance Goals**: `POST /v1/infer` p99 < 50 ms / p50 < 10 ms（CPU、warm policy、100 並發）；`POST /v1/episode/run` 1 年區間 < 5 秒、8 年 < 30 秒。
**Constraints**: stateless、無資料庫、推理結果與 003+004 直接執行 byte-identical（容差 0.0）；OpenAPI spec commit 入 repo（FR-017）；不做 auth/TLS（由 006 Gateway / ingress 處理）。
**Scale/Scope**: 同時 ≤ 10 個 policy 常駐（總 RAM < 100 MB）；100 並發推理請求；單機部署（不做 horizontal scaling 或 sticky session）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依憲法 v1.1.0 五大原則逐項評估：

### Principle I — 可重現性（NON-NEGOTIABLE）

✅ **PASS**

- 推理路徑使用 `policy.predict(obs, deterministic=True)`，無亂數源 → 同 obs 同 policy 兩次推理 byte-identical（FR-020、SC-005）。
- Episode 推理 API 接受 `seed` 參數，內部建構 003 PortfolioEnv 時呼叫 `env.reset(seed=seed)`，與 004 的 4-layer PRNG 同步策略一致 → 同參數兩次 episode byte-identical（FR-021、SC-004）。
- `policy_id` 對應 PolicyHandle 含 004 metadata.json 完整內容（`git_commit_hash`、`data_hashes`、`package_versions`），可透過 `GET /v1/policies` 追溯到訓練 commit。
- 服務不寫任何 mutable state；無快取造成的非決定性。

### Principle II — 特徵可解釋性

✅ **PASS**

- `POST /v1/episode/run` 回傳每步 `info` 含 SMC 訊號 raw 值（`bos`、`choch`、`fvg_distance_pct`、`ob_touch_state` 等，沿用 003 info schema），前端可直接視覺化。
- `reward_components_estimate` 將 reward 三項分量（log_return、drawdown_penalty、turnover_penalty）拆開回傳，避免黑箱聚合（FR-001）。
- OpenAPI 3.1 spec 對外公開所有 schema，下游可程式化解析。

### Principle III — 風險優先獎勵（NON-NEGOTIABLE）

✅ **N/A 但有對應**

- 本 feature 不定義 reward function（屬 003 + 004），但 inference response 之 `reward_components_estimate` MUST 與 003 reward 三項分量結構一致（log_return、drawdown_penalty、turnover_penalty）→ 不允許退化成單一純報酬欄位。
- API schema 強制三項分開，從介面層守住 Principle III。

### Principle IV — 微服務解耦

✅ **PASS（核心對應）**

- 本 feature 即 Principle IV 中「Python AI 引擎」一層的具體實作。
- 對外只透過 HTTP API 溝通（FastAPI → uvicorn → 006 Gateway），無共享資料庫、無共享行程記憶體。
- OpenAPI 3.1 spec 為跨服務契約來源（FR-015、FR-017），006 Java client stub 從此檔生成（gRPC / Protobuf 不採用，理由見 research.md R4）。
- 服務 stateless 可獨立部署、獨立水平擴展（雖本 feature 範圍內 scope 為單機）。

### Principle V — 規格先行（NON-NEGOTIABLE）

✅ **PASS**

- spec.md 已通過 quality checklist（specs/005-inference-service/checklists/requirements.md）。
- 本 plan 之 contracts/ 為「先寫契約再實作」，OpenAPI 3.1 + JSON schema 明文。
- tasks.md 排程顯示先寫 contract test、再寫實作（TDD 內含）。

**Initial Constitution Check 結論**：所有 5 條原則無違反；無需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/005-inference-service/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── openapi.yaml     # OpenAPI 3.1 spec (主契約)
│   ├── error-codes.md   # 錯誤碼一覽 + 訊息規約
│   └── episode-log.schema.json  # episode_log 元素 schema (引用 003)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/inference_service/
├── __init__.py
├── __main__.py              # uvicorn 啟動入口
├── app.py                   # FastAPI app + router 註冊
├── config.py                # ServiceConfig dataclass + env var 解析
├── policies/
│   ├── __init__.py
│   ├── handle.py            # PolicyHandle dataclass + load/predict 邏輯
│   ├── registry.py          # PolicyRegistry (dict[str, PolicyHandle])
│   └── loader.py            # 從 zip + metadata.json 載入 policy
├── routers/
│   ├── __init__.py
│   ├── infer.py             # POST /v1/infer
│   ├── episode.py           # POST /v1/episode/run + /v1/episode/stream
│   ├── policies.py          # GET/POST/DELETE /v1/policies
│   └── ops.py               # /healthz, /readyz, /metrics
├── schemas/
│   ├── __init__.py
│   ├── infer.py             # Pydantic models (InferenceRequest/Response)
│   ├── episode.py           # EpisodeRequest/Response/EpisodeLogEntry
│   └── policy.py            # PolicyMetadata
├── observability/
│   ├── __init__.py
│   ├── logging.py           # 結構化 JSON logger
│   └── metrics.py           # Prometheus 指標定義
└── errors.py                # 例外定義 + HTTP exception handler

tests/
├── contract/
│   ├── test_openapi_validity.py    # openapi-spec-validator
│   ├── test_infer_schema.py        # POST /v1/infer 回應 schema
│   ├── test_episode_schema.py      # POST /v1/episode/run 回應 schema
│   └── test_policies_schema.py
├── integration/
│   ├── test_infer_byte_identical.py  # 同 obs 兩次推理一致
│   ├── test_episode_vs_env.py        # /v1/episode/run vs 直接跑 003 byte-identical
│   ├── test_concurrent_inference.py  # 100 並發 latency budget
│   ├── test_policy_lifecycle.py      # 載入/推理/卸載
│   └── test_health_metrics.py        # /healthz, /readyz, /metrics
└── unit/
    ├── test_policy_handle.py
    ├── test_registry.py
    ├── test_config.py
    └── test_logging.py
```

**Structure Decision**: Single project layout，純 Python 後端服務 package。`src/inference_service/` 為 importable package（`pyproject.toml` 之 `[project] name = "inference_service"`），可由 006 之整合測試或 007 之 e2e 測試以 subprocess 啟動。OpenAPI yaml 既由 FastAPI 動態產生（`/openapi.json`），亦於 CI 流程中**寫出靜態 `contracts/openapi.yaml` 並 commit**（FR-017），確保 006 client stub 生成不依賴執行中服務。

## Complexity Tracking

> 無違反 Constitution，本節不適用。
