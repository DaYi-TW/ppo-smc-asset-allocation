# Quickstart: Spring Gateway

> **🚫 SUPERSEDED（2026-05-06）**：本檔描述 Postgres + Kafka + MinIO 的 docker-compose 起法，C-lite v2 已**移除這些相依**。C-lite v2 quickstart（Gateway + 005 + Redis 三 service docker-compose、5 分鐘端對端）將由下一輪 `/speckit.plan` 重新產生於同檔。本檔禁止用於 implementation。

---

5 分鐘內以 docker-compose 啟動 Gateway + 005 + Postgres + Kafka + MinIO，跑通端對端 inference 與 episode。

## 前置條件

1. **Docker** 24+ + **docker-compose** v2。
2. **Java 17+** + **Maven 3.9+**（本地 IDE 開發用；docker build 不需 host 安裝）。
3. **005 推理服務** 已實作完成、Docker image 可建。
4. **004 訓練 artefact** 至少一份 `final_policy.zip` + `metadata.json`，掛載至容器 `/policies/`。

## 安裝

```bash
cd services/gateway
mvn clean package -DskipTests
```

`mvn package` 將：

1. 自 `../../specs/005-inference-service/contracts/openapi.yaml` 產生 005 Java client（`target/generated-sources/openapi/`）。
2. 編譯 + 打包 Spring Boot fat jar 至 `target/gateway-1.0.0.jar`。
3. （可選）`mvn verify` 跑全部 unit + IT（需 Docker 跑 testcontainers）。

## 啟動全 stack（local dev）

```bash
cd services/gateway
docker-compose up -d
```

`docker-compose.yml` 啟動：

- `gateway`（Spring Boot，port 8080）
- `inference`（005 服務，port 8000，掛載 `./policies/` 與 `./data/raw/`）
- `postgres` (port 5432, db=`gateway`, user=`gateway`, pwd=`gateway`)
- `kafka` (port 9092；Bitnami Kafka image，KRaft mode 無需 zookeeper)
- `minio` (port 9000 console, port 9001 S3 API；access_key=`minio`, secret=`minio12345`)

**啟動 log（預期 30 秒內）**：

```text
gateway     | Started GatewayApplication in 12.3 seconds
gateway     | Schema migrations applied: V1__init_schema → 1
gateway     | Connected to Kafka bootstrap.servers=kafka:9092
gateway     | Inference client base URL: http://inference:8000
```

## 取得 JWT token（demo）

```bash
# 本 feature 不負責 JWT 簽發；demo 用 jwt.io 或 Python script 簽
python <<'EOF'
import jwt, datetime
secret = "demo-signing-key-at-least-256-bits-long-for-hs256-algorithm"  # 與 docker-compose env 一致
token = jwt.encode({
    "sub": "researcher@example.com",
    "role": "researcher",
    "iat": datetime.datetime.utcnow(),
    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
}, secret, algorithm="HS256")
print(token)
EOF
# 將輸出 token 存成 $TOKEN
export TOKEN=eyJhbGciOiJIUzI1NiIs...
```

## 1. 健康檢查

```bash
curl http://localhost:8080/actuator/health | jq
# {
#   "status": "UP",
#   "components": {
#     "inferenceService": { "status": "UP" },
#     "kafka": { "status": "UP" },
#     "db": { "status": "UP" }
#   }
# }
```

## 2. 列出已載入 policy

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/policies | jq
```

## 3. 單筆推理

```bash
curl -X POST http://localhost:8080/api/v1/inference/infer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "observation": [0.0, 0.1, ... 63 floats ...],
    "deterministic": true
  }' | jq
```

預期回應（camelCase）：

```json
{
  "inferenceId": "uuid",
  "requestId": "uuid",
  "policyId": "baseline_seed1",
  "action": [0.10, 0.18, 0.18, 0.18, 0.06, 0.15, 0.15],
  "value": 0.024,
  "logProb": -2.31,
  "rewardComponentsEstimate": null,
  "inferenceLatencyMs": 7.2,
  "gatewayLatencyMs": 4.8,
  "serverUtc": "2026-04-29T12:01:00Z"
}
```

p99 端對端 < 100 ms（SC-001）。

## 4. 非同步 episode 推理

```bash
# Submit
curl -X POST http://localhost:8080/api/v1/episode/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "policyId": "baseline_seed1",
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
    "includeSmc": true,
    "seed": 1
  }' | jq

# {
#   "taskId": "uuid",
#   "status": "pending",
#   "pollUrl": "/api/v1/tasks/uuid",
#   "streamUrl": "/api/v1/tasks/uuid/stream"
# }

# Poll
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/tasks/<taskId> | jq

# 或 SSE
curl -N -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/tasks/<taskId>/stream
# event: progress
# data: {"status":"running","progressPct":35}
# event: done
# data: {"status":"completed","summary":{...},"trajectoryUrl":"..."}
```

100 並發任務 60 秒內完成（SC-002）。

## 5. 重試與 idempotency

```bash
# 同 Idempotency-Key 提交兩次 → 回相同 taskId
KEY=$(uuidgen)
curl -X POST .../episode/run -H "Idempotency-Key: $KEY" -d '...'
curl -X POST .../episode/run -H "Idempotency-Key: $KEY" -d '...'  # 同 taskId
```

## 6. 載入新 policy（admin）

```bash
curl -X POST http://localhost:8080/api/v1/policies/load \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "policyPath": "/policies/runs/.../final_policy.zip",
    "policyId": "ablation_seed1"
  }'
```

## 7. 查詢歷史紀錄

```bash
# Inference log（分頁）
curl "http://localhost:8080/api/v1/logs/inferences?policyId=baseline_seed1&limit=50" \
  -H "Authorization: Bearer $TOKEN" | jq

# Episode log
curl "http://localhost:8080/api/v1/logs/episodes/<episodeId>" \
  -H "Authorization: Bearer $TOKEN" | jq

# Export NDJSON
curl "http://localhost:8080/api/v1/logs/inferences/export?format=ndjson&from=2026-04-01T00:00:00Z" \
  -H "Authorization: Bearer $TOKEN" > inference_log.ndjson
```

## 8. 熔斷器演練（SC-003）

```bash
# 故意停掉 005
docker-compose stop inference

# 連續打 inference API
for i in {1..20}; do
  curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
    -X POST http://localhost:8080/api/v1/inference/infer \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"observation":[0.0,...]}'
done

# 預期：前 5-10 個 504（timeout）後 circuit OPEN；
#       接著的請求 100ms 內回 503 INFERENCE_SERVICE_UNAVAILABLE。

# 恢復
docker-compose start inference
sleep 35  # circuit 30s 後 HALF_OPEN
curl ... # 正常 200
```

## 9. Prometheus metrics

```bash
curl http://localhost:8080/actuator/prometheus | grep -E "(inference_proxy_latency|kafka_consumer_lag|task_completion)"
```

## 10. OpenAPI spec 同步

```bash
# 服務跑著時 dump 最新
curl http://localhost:8080/v3/api-docs.yaml > /tmp/runtime.yaml

# CI 跑此檢查
diff specs/006-spring-gateway/contracts/openapi.yaml /tmp/runtime.yaml
# 預期：無差異
```

## 跑 unit + integration 測試

```bash
mvn verify
# 預期：覆蓋率 ≥ 80%（SC-005）
```

## 常見問題

**Q: 啟動時報 `Cannot find inference yaml`？**
A: 確認 monorepo root 在 build 時 mounted 進容器；`pom.xml` 之 openapi-generator-maven-plugin `inputSpec` 指向 `${project.basedir}/../../specs/005-inference-service/contracts/openapi.yaml` 必須相對 path 正確。

**Q: testcontainers 啟動超慢？**
A: 預先 `docker pull postgres:14 confluentinc/cp-kafka:7.5.0 minio/minio:latest`；CI 用 cache。

**Q: Kafka producer 寫 `episode-tasks` 失敗？**
A: 檢查 `KAFKA_BOOTSTRAP_SERVERS` env、確認 topic 已建（首次啟動 auto-create）；本地用 `docker-compose exec kafka kafka-topics --list --bootstrap-server kafka:9092`。

**Q: `POST /api/v1/policies/load` 回 403？**
A: JWT claim `role` 不為 `researcher`；用 reviewer token 不能寫操作（FR-017）。

**Q: trajectory 預期落地 S3 但結果 inline？**
A: trajectory < 1 MB 才 inline；想強制測 S3 路徑可呼叫 `/api/v1/episode/run` 多年區間（生成 > 1 MB JSON）。
