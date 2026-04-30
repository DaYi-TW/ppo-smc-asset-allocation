# Quickstart: 推理服務

5 分鐘內啟動推理服務、跑一次推理與一次 episode。

## 前置條件

1. **003 已完成**：`portfolio_env` package 可 `pip install -e .`、`PortfolioEnv-v0` 已註冊。
2. **004 已完成**：至少一個 `final_policy.zip` 與同目錄 `metadata.json`。
3. Python 3.11+。

## 安裝

```bash
# 在專案根目錄
pip install -e ".[inference]"
# optional dependencies [inference] 包含：
#   fastapi, uvicorn[standard], stable-baselines3, prometheus-client,
#   sse-starlette, pydantic, orjson, PyYAML
```

## 啟動服務

```bash
# 方式 A：用 default policy 環境變數
export INFERENCE_DEFAULT_POLICY_PATH=runs/20260429_141523_a0acd02_seed1/final_policy.zip
export INFERENCE_DEFAULT_POLICY_ID=baseline_seed1
python -m inference_service

# 方式 B：CLI flag
python -m inference_service \
    --default-policy-path runs/.../final_policy.zip \
    --default-policy-id baseline_seed1 \
    --port 8000
```

**啟動 log（預期 < 5 秒）**：

```text
{"timestamp":"2026-04-29T12:00:00Z","level":"INFO","event":"service_started","port":8000}
{"timestamp":"2026-04-29T12:00:01Z","level":"INFO","event":"policy_loaded","policy_id":"baseline_seed1","obs_dim":63}
{"timestamp":"2026-04-29T12:00:01Z","level":"INFO","event":"ready"}
```

## 1. 健康檢查

```bash
curl http://localhost:8000/healthz
# {"status":"ok","uptime_seconds":12,"server_utc":"2026-04-29T12:00:12Z"}

curl http://localhost:8000/readyz
# {"status":"ready","policies_loaded":1}

curl http://localhost:8000/metrics | head -20
# # HELP inference_requests_total ...
```

## 2. 單筆推理

```bash
# obs 為 63 維（include_smc=true）
curl -X POST http://localhost:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{
    "observation": [0.0, 0.1, ... 63 floats ...],
    "deterministic": true
  }'
```

**預期回應**：

```json
{
  "inference_id": "8f3a...",
  "policy_id": "baseline_seed1",
  "action": [0.10, 0.18, 0.18, 0.18, 0.06, 0.15, 0.15],
  "value": 0.024,
  "log_prob": -2.31,
  "reward_components_estimate": null,
  "latency_ms": 7.2,
  "server_utc": "2026-04-29T12:01:00Z"
}
```

p99 latency MUST < 50 ms（單機 CPU、warm policy）。

## 3. Episode 推理

```bash
curl -X POST http://localhost:8000/v1/episode/run \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "baseline_seed1",
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "include_smc": true,
    "seed": 1,
    "deterministic": true
  }' | jq '.episode_summary'
```

**預期 summary**（單年區間 < 5 秒）：

```json
{
  "final_nav": 1.082,
  "peak_nav": 1.124,
  "max_drawdown": 0.085,
  "sharpe_ratio": 1.34,
  "sortino_ratio": 1.87,
  "total_return": 0.082,
  "annualized_return": 0.082,
  "annualized_volatility": 0.061,
  "num_trades": 18,
  "avg_turnover": 0.043
}
```

## 4. SSE Streaming（episode 動畫）

```bash
curl -N -X POST 'http://localhost:8000/v1/episode/stream?step_chunk=20' \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "baseline_seed1",
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "seed": 1
  }'
```

**輸出**：

```text
event: progress
id: 20
data: {"step":20,"total_steps":252,"weights":[...],"nav":1.012,"drawdown":0.005}

event: progress
id: 40
data: {"step":40,...}

...

event: done
id: final
data: {"episode_summary":{...},"elapsed_seconds":4.2}
```

## 5. Policy 管理

```bash
# 列出已載入
curl http://localhost:8000/v1/policies | jq

# 動態載入新 policy
curl -X POST http://localhost:8000/v1/policies/load \
  -H "Content-Type: application/json" \
  -d '{
    "policy_path": "runs/20260430_080000_b1c2d3e_seed1/final_policy.zip",
    "policy_id": "ablation_seed1"
  }'

# 用新 policy 推理
curl -X POST http://localhost:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{"observation": [...], "policy_id": "ablation_seed1"}'

# 卸載
curl -X DELETE http://localhost:8000/v1/policies/ablation_seed1
```

## 6. 跨層 byte-identical 驗證（SC-004）

```bash
# A. API 跑 episode
curl -X POST http://localhost:8000/v1/episode/run \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/episode_request_2025.json | jq '.episode_log' > /tmp/api_log.json

# B. 直接 import 003 + 004 跑同樣 episode
python tests/integration/run_episode_directly.py \
  --policy runs/.../final_policy.zip \
  --start 2025-01-01 --end 2025-12-31 --seed 1 > /tmp/direct_log.json

# C. byte-identical 比對
diff /tmp/api_log.json /tmp/direct_log.json
# 預期：無差異（exit 0）
```

## 7. OpenAPI spec 同步（contracts/openapi.yaml）

```bash
# 服務跑著時 dump 最新 schema
curl http://localhost:8000/openapi.json | python -m json.tool > /tmp/runtime_openapi.json

# 與 commit 中的 yaml 比對
python -m inference_service dump-openapi --output /tmp/dumped.yaml
diff specs/005-inference-service/contracts/openapi.yaml /tmp/dumped.yaml
# CI 會跑此檢查；若不一致需重新 commit yaml
```

## 8. 並發負載測試（SC-006）

```bash
# 用 hey 或 wrk 模擬 100 並發
hey -n 10000 -c 100 -m POST -T application/json \
    -d '{"observation":[0.0,...]}' \
    http://localhost:8000/v1/infer

# 預期：
#   p99 < 50 ms
#   p50 < 10 ms
#   無 5xx 錯誤
```

## 9. 跑單元 + 整合測試

```bash
pytest tests/ -v --cov=src/inference_service --cov-report=term-missing
# 預期：覆蓋率 ≥ 85%（SC-007）
```

## 常見問題

**Q: `/readyz` 一直 503？**
A: 看啟動 log 之 `policy_loaded` 是否出現；若無，policy_path 錯或 zip 損毀。`/healthz` 仍 200，K8s 不會重啟容器。

**Q: 推理 latency p99 > 50 ms？**
A: (a) 確認 `INFERENCE_DEFAULT_POLICY_PATH` 為 SSD；(b) 確認服務未跑在 cgroup CPU throttling 環境；(c) `policy.predict` 是否被同步包在 thread pool（`asyncio.to_thread`）。

**Q: 兩次相同請求 action 不一致？**
A: 確認 `deterministic=true`；stochastic 模式 sb3 內部抽樣有隨機性。

**Q: episode 跑 8 年區間 OOM？**
A: 將 episode_log 改用 SSE streaming（`/v1/episode/stream`）逐步消費；或縮短區間後分段請求。

**Q: 006 Java client 從 yaml 生成失敗？**
A: 確認用 openapi-generator-cli ≥ 7.0（支援 OpenAPI 3.1）；舊版 6.x 不支援 nullable union type。
