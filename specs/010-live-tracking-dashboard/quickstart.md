# Quickstart: PPO Live Tracking Dashboard (010)

**Audience**: 第一次跑本 feature 端到端的開發者 / 我自己（一週後）。
**Pre-req**: 009 已落地（OOS episode_detail.json 存在於 `runs/<policy_run_id>/episode_detail.json`），005 + 006 服務鏡像已 build。

---

## 1. 準備 baked policy + OOS artefact (從 009)

```bash
# 確認 OOS episode artefact 存在
ls runs/20260506_004455_659b8eb_seed42/episode_detail.json

# 確認 baked policy 存在（005 lifespan eager load 用）
ls runs/20260506_004455_659b8eb_seed42/policy.zip
```

若任一缺失：先回 009 跑 `python scripts/run_oos_evaluator.py` + `python scripts/build_episode_artifact.py`。

---

## 2. 起 dev 容器

```bash
docker compose -f infra/docker-compose.gateway.yml up --build
```

預期看到：
- `inference-service` (port 8000) healthy
- `spring-gateway` (port 8080) healthy
- 啟動 log 含 `live_tracking_status_recovered_orphan: false`（首次啟動 status file 不存在，跳過 orphan check）

---

## 3. 確認 episodes list 同時含 OOS + Live entry

```bash
curl -s http://localhost:8080/api/v1/episodes | jq
```

預期 response：

```json
{
  "items": [
    {
      "episode_id": "20260506_004455_659b8eb_seed42",
      "source": "oos",
      "horizon": 329,
      "final_nav": 1.7291986,
      ...
    },
    {
      "episode_id": "20260506_004455_659b8eb_seed42_live",
      "source": "live",
      "horizon": 0,
      "final_nav": 1.0,
      ...
    }
  ]
}
```

OOS 一定排前面（R5）。Live entry 在首次 refresh 前 `horizon=0`。

---

## 4. 第一次 refresh — 從 2026-04-29 補齊到今天

```bash
curl -s -X POST http://localhost:8080/api/v1/episodes/live/refresh | jq
```

預期 202：

```json
{
  "accepted": true,
  "pipeline_id": "550e8400-...",
  "estimated_duration_seconds": 8,
  "poll_status_url": "/api/v1/episodes/live/status"
}
```

---

## 5. Polling status

```bash
# 重複至 is_running=false
watch -n 1 'curl -s http://localhost:8080/api/v1/episodes/live/status | jq'
```

完成後預期：

```json
{
  "last_updated": "2026-05-08T14:00:01Z",
  "last_frame_date": "2026-05-07",
  "data_lag_days": 1,
  "is_running": false,
  "last_error": null
}
```

`data_lag_days` 取決於今天是否為交易日 / 是否盤後跑。

---

## 6. 驗 artefact 落地

```bash
ls runs/20260506_004455_659b8eb_seed42/live_tracking/
# live_tracking.json
# live_tracking_status.json

jq '.trajectoryInline | length' runs/20260506_004455_659b8eb_seed42/live_tracking/live_tracking.json
# 預期 >= 1（至少 2026-04-29 一個 frame）

jq '.trajectoryInline[0].t' runs/20260506_004455_659b8eb_seed42/live_tracking/live_tracking.json
# "2026-04-29"
```

---

## 7. 並發保護（SC-004）

開兩個 terminal 同時：

```bash
# Terminal A
curl -X POST http://localhost:8080/api/v1/episodes/live/refresh

# Terminal B (同時)
curl -X POST http://localhost:8080/api/v1/episodes/live/refresh
```

A 應拿到 202，B 應拿到 409：

```json
{
  "detail": "pipeline already running",
  "running_pid": 12345,
  "running_started_at": "2026-05-08T14:05:00Z",
  "poll_status_url": "/api/v1/episodes/live/status"
}
```

---

## 8. 失敗回滾驗證（SC-005）

模擬 fetch 失敗：暫時關掉 yfinance 出口 / 改 BAD_TICKER：

```bash
LIVE_TRACKER_FORCE_FETCH_ERROR=1 curl -X POST http://localhost:8080/api/v1/episodes/live/refresh
# 等 pipeline 失敗

curl -s http://localhost:8080/api/v1/episodes/live/status | jq
# is_running: false
# last_error: "DATA_FETCH: yfinance returned empty for NVDA on 2026-05-08"

# artefact 不變（檢查 mtime + 行數）
stat -c '%y %s' runs/20260506_004455_659b8eb_seed42/live_tracking/live_tracking.json
```

---

## 9. 前端 Overview 整合

```bash
cd apps/web && pnpm dev
# 開 http://localhost:5173/overview
```

預期：
- Header 標題 `Live Tracking — <policy_run_id>`
- 右上角 badge「資料截至 1 天前」
- 「手動更新到最新」按鈕
- 點按鈕 → 按鈕 disabled + spinner → polling 完成 → NAV 線、權重、SMC 重繪

OOS 仍可從左側 EpisodeList 點進去（id 不含 `_live`）。

---

## 10. Constitution gate sanity

```bash
# Principle I (OOS hash)
docker compose run --rm inference-service \
  pytest tests/contract/episode_artifact/test_oos_immutable_hash.py -v

# Principle I (Live append-only)
docker compose run --rm inference-service \
  pytest tests/contract/live_tracking/test_append_only.py -v

# Principle III (reward parity)
docker compose run --rm inference-service \
  pytest tests/contract/live_tracking/test_reward_parity.py -v
```

三條全綠才可推 PR。

---

## Troubleshooting

| 症狀 | 原因 | 修法 |
|------|------|------|
| `is_running` 卡 True 不會降 | 上次 process 被 SIGKILL，orphan lock 沒清 | 重啟 005 → lifespan 自動 recover；或手動刪 status.json |
| 第一次 refresh 回 404 not found | live id 不在 episodes list | 確認 005 lifespan 有 register live store（見 `app.py`） |
| `data_lag_days` 顯示 0 但週末跑 | 期望行為（NYSE 週六/日無交易日，last_frame_date 停在上週五） | 不是 bug |
| OOS hash test 失敗 | `build_episode_artifact.py` 被改 | 回 009 找出 diff，本 feature 禁止動 OOS pipeline |
