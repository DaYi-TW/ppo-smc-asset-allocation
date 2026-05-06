# Quickstart: 推理服務（005-inference-service）— C-lite 版

**Last Major Revision**: 2026-05-06

5 分鐘內在本機跑通 inference service，發出第一個 prediction event 到 Redis。

## 前置條件

1. **004 已產出 policy**：至少一個 `runs/<run_id>/final_policy.zip`（與其同目錄的 `metadata.json` 屬可選）。本範例用 `runs/20260506_004455_659b8eb_seed42/`。
2. **002 已產出資料**：`data/raw/*.parquet`（8 個資產 + DTB3）已 commit 或本地存在。資料新鮮度由 `ppo-smc-data update` 維護。
3. **Docker Desktop**（macOS / Windows / WSL2）或 **Docker Engine + Compose**（Linux）。
4. （可選）Python 3.11+ 本機環境，用於不走 docker 直接啟動服務驗證。

## 路徑 A：本機 docker-compose（推薦）

### 1. Build image

```bash
docker compose -f infra/docker-compose.inference.yml build \
    --build-arg POLICY_RUN_ID=20260506_004455_659b8eb_seed42
```

預期：~60 秒（首次 layer cache 冷），後續 < 10 秒。

### 2. 啟動

```bash
docker compose -f infra/docker-compose.inference.yml up -d
```

預期：
- `redis` container 5 秒內 ready
- `python-infer` container 60 秒內 healthy（policy 載入 + scheduler 註冊）

### 3. Smoke test

```bash
# 健康檢查
curl http://localhost:8000/healthz
# 預期：200 + {"status":"ok","policy_loaded":true,"redis_reachable":true,...}

# 觸發一次 inference（最久 90 秒）
time curl -X POST http://localhost:8000/infer/run
# 預期：200 + PredictionPayload JSON，target_weights 7 維 sum≈1

# 取最新一筆（從 Redis cache 讀）
curl http://localhost:8000/infer/latest
# 預期：200 + 同上 JSON
```

### 4. 觀察 Redis pub/sub

開另一個 terminal：

```bash
docker compose -f infra/docker-compose.inference.yml exec redis redis-cli SUBSCRIBE predictions:latest
```

回到原 terminal 再跑一次 `POST /infer/run`，預期 redis-cli 視窗會看到一筆 message。

### 5. 觀察 scheduled trigger（選擇性）

scheduler 預設 `30 16 * * MON-FRI` ET（台北 05:30），等下一個 trigger 點即可看到自動推理。臨時測試可改 env var：

```bash
SCHEDULE_CRON="*/2 * * * *" docker compose -f infra/docker-compose.inference.yml up
```

（每 2 分鐘觸發一次，僅供驗證）

## 路徑 B：本機直跑（不走 docker，僅供 dev 階段）

### 1. 安裝

```bash
pip install -e ".[inference]"
```

### 2. 起 Redis

```bash
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine
```

### 3. 啟動 service

```bash
export POLICY_PATH=runs/20260506_004455_659b8eb_seed42/final_policy.zip
export DATA_ROOT=data/raw
export REDIS_URL=redis://localhost:6379/0
python -m inference_service
```

預期：~10 秒內 uvicorn 印出 `Uvicorn running on http://0.0.0.0:8000`。

### 4. 同樣跑 smoke test（同路徑 A 的 Step 3）

## 跑測試

```bash
pytest tests/unit/inference_service/ tests/integration/inference_service/ tests/contract/inference_service/ -v
```

預期：全綠，coverage ≥ 85%。

## 常見錯誤排除

| 症狀 | 可能原因 | 處理 |
|------|----------|------|
| `/healthz` 回 503 + `policy_loaded:false` | `POLICY_PATH` 指向不存在或損毀的 zip | 確認 path、`unzip -l` 看 archive 內容 |
| `/healthz` 回 503 + `redis_reachable:false` | Redis container 沒起或 `REDIS_URL` 錯 | `docker compose ps`、檢查 env var |
| `/infer/run` 回 409 INFERENCE_BUSY | 上一次 inference 還沒跑完（< 90 秒） | 等 1 分鐘 retry |
| `/infer/latest` 回 404 NO_PREDICTION_YET | 服務剛啟動還沒跑過 inference | 先 `POST /infer/run` 或等 scheduled trigger |
| scheduled trigger 沒 fire | timezone 設錯 / cron 格式錯 | 檢查 `SCHEDULE_TIMEZONE=America/New_York`、`SCHEDULE_CRON` 用 5-field crontab |
| inference 跑 > 90 秒 | data/raw 過期或 policy 載入路徑錯 | 看 stdout log，找 `event=inference_started` 後的時序 |

## 部署到 Zeabur（Phase 2，後續）

1. 在 Zeabur 建立新 project
2. 加 Redis service（Zeabur add-on）
3. 從 GitHub repo 部署 `infra/Dockerfile.inference`
4. 設 env var：`POLICY_PATH`, `DATA_ROOT`, `REDIS_URL`（Zeabur 自動 inject Redis URL）, `SCHEDULE_CRON`
5. Health check path 設 `/healthz`，timeout 60 秒

詳細步驟待 Phase 2 上線時補。

## 下一步

- 跑通本 quickstart 後，繼續 006 Spring Gateway（subscribe `predictions:latest` channel + SSE 廣播）
- 或先回 007 War Room 加 `LivePredictionCard`（直接讀 Redis 不經 Gateway）

## 相關文件

- [spec.md](./spec.md)：功能需求
- [plan.md](./plan.md)：技術計畫
- [data-model.md](./data-model.md)：schema 細節
- [contracts/openapi.yaml](./contracts/openapi.yaml)：完整 OpenAPI 3.1 spec
- [contracts/error-codes.md](./contracts/error-codes.md)：錯誤碼字典
