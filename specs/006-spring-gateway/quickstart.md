# Quickstart: Spring Gateway (C-lite v2)

5 分鐘以 docker-compose 起 spring-gw + python-infer + redis 三個 service，跑通 REST proxy + SSE 廣播。

## 前置條件

1. **Docker** 24+ + **docker-compose** v2.
2. **Java 21** + **Maven 3.9+**（僅本地 IDE 開發用；docker build 不需 host 安裝）.
3. **005 已 build 好**：`runs/<POLICY_RUN_ID>/final_policy.zip` 存在、`data/raw/*.parquet` 存在.

## Path A: 本機 docker-compose（含 005 + Gateway + Redis）

```bash
# repo root
export POLICY_RUN_ID=20260506_004455_659b8eb_seed42
docker compose -f infra/docker-compose.gateway.yml up --build
```

驗證（另開 terminal）：

```bash
# 1. Gateway 自身 health
curl -fsS http://localhost:8080/actuator/health | jq .
# 預期：{"status":"UP","components":{"inference":{"status":"UP",...},"redis":{"status":"UP"}}}

# 2. proxy GET /infer/latest（需先有 prediction）
curl -fsS http://localhost:8080/api/v1/inference/latest | jq .
# 若 cache 為空，回 404 PredictionNotReady

# 3. 觸發一次 inference
curl -fsSX POST http://localhost:8080/api/v1/inference/run | jq .targetWeights
# 預期：{"NVDA":0.1, "AMD":0.1, ..., "CASH":0.4}（camelCase + 7 個 key sum=1.0）

# 4. SSE 訂閱（保持連線）
curl -N http://localhost:8080/api/v1/predictions/stream
# 預期立即收到一筆 initial state（FR-007），之後每收到 005 publish 一筆 prediction event
# 也會每 15s 收到 :ping comment（FR-008 keep-alive）

# 5. 模擬 005 publish（另開 terminal）
docker exec -it $(docker ps -qf name=redis) redis-cli PUBLISH predictions:latest '{"as_of_date":"2026-05-06",...}'
# 訂閱端應立即收到 event: prediction
```

## Path B: 純 Maven dev（無 docker；需 host 有 redis + 005）

```bash
cd services/gateway
# 配置：application.yaml 預設指向 host.docker.internal；本機 dev 改用環境變數
INFERENCE_URL=http://localhost:8000 \
REDIS_URL=redis://localhost:6379/0 \
mvn spring-boot:run

# 在另一 terminal 確保 005 + redis 在跑（用 005 的 docker-compose）
docker compose -f infra/docker-compose.inference.yml up
```

## 常見錯誤排除

| 症狀 | 原因 | 解法 |
|---|---|---|
| `/actuator/health` 200 但 inference component DOWN | 005 連不到（容器網路 / URL 錯） | 檢查 `INFERENCE_URL` 環境變數；docker compose 內服務名應為 `python-infer` |
| `/actuator/health` redis component DOWN | Redis 連不到 | 檢查 `REDIS_URL`；docker network 是否同一 bridge |
| `POST /api/v1/inference/run` 504 InferenceTimeout | 005 inference 跑超過 90s（cold start env warmup） | 重跑一次（warmup 後 cache 命中 < 5s）；若持續 504 檢查 005 stderr 是否 OOM |
| `POST /api/v1/inference/run` 503 InferenceServiceUnavailable | 005 進程 down | `docker logs python-infer`；確認 policy zip 路徑正確 |
| SSE 訂閱端收不到 event | Redis listener 未啟動 / channel 名稱錯 | 看 Gateway log 找 `redis_subscription_started`；確認 `REDIS_CHANNEL=predictions:latest` |
| SSE 訂閱中途斷連 | Zeabur edge proxy 60s timeout | 確認 keep-alive ping 已開（每 15s 一次 `:\n\n`）；若仍斷查 Zeabur dashboard timeout 設定 |
| CORS preflight 403 | origin 不在白名單 | 設 `CORS_ALLOWED_ORIGINS=http://localhost:5173,https://your-prod.example.com` |
| Maven build 失敗：`Unsupported class file major version 65` | host JDK 版本 < 21 | 升級 JDK 21 或改用 docker build（`docker build -f services/gateway/Dockerfile`） |

## 開發者快速指令

```bash
# 跑單元測試（不需 docker）
cd services/gateway && mvn test

# 跑整合測試（需 docker daemon — testcontainers Redis）
cd services/gateway && mvn verify

# 抓即時 OpenAPI（Gateway 跑著時）
curl -fsS http://localhost:8080/v3/api-docs | jq .

# 看 Swagger UI（Phase 6 啟用時）
open http://localhost:8080/swagger-ui.html
```
