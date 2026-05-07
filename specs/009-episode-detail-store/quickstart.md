# Quickstart: PPO Episode Detail Store

**Feature**: 009-episode-detail-store
**Audience**: 在乾淨環境驗證整條 evaluator → builder → 005 → 006 → 007 端對端的開發者

## 前置

- 已有 trained policy：`runs/20260506_004455_659b8eb_seed42/final_policy.zip`
- 已有 OOS data snapshot：`data/raw/{NVDA,AMD,TSM,MU,GLD,TLT}_oos.parquet`
- Docker（含 compose v2）已安裝
- Python 3.11 + 既有 venv（或 dev container）

## 步驟 1：跑 evaluator（產 trajectory.parquet + legacy CSV + eval_summary.json）

```bash
python -m ppo_training.evaluate \
    --policy runs/20260506_004455_659b8eb_seed42/final_policy.zip \
    --data-root data/raw \
    --start-date 2025-01-02 \
    --end-date 2026-04-28 \
    --seed 42 \
    --save-trajectory
```

預期輸出：
```
runs/20260506_004455_659b8eb_seed42/eval_oos/eval_summary.json
runs/20260506_004455_659b8eb_seed42/eval_oos/trajectory.parquet
runs/20260506_004455_659b8eb_seed42/eval_oos/trajectory.csv     # legacy
```

驗證：
```bash
python -c "import pandas as pd; df = pd.read_parquet('runs/20260506_004455_659b8eb_seed42/eval_oos/trajectory.parquet'); print(df.columns.tolist()); print(df.shape)"
```
應印 70+ columns、(330, N)（含 step=0 起始 frame）。

## 步驟 2：build episode artefact

```bash
python scripts/build_episode_artifact.py \
    --run-dir runs/20260506_004455_659b8eb_seed42 \
    --data-root data/raw \
    --output infra/inference/artefact/episode_detail.json
```

預期 console 輸出：
```
[builder] trajectoryInline frames: 330
[builder] rewardBreakdown.byStep entries: 329
[builder] smcOverlayByAsset assets: ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT']
[builder] artefact size: 5.2 MB
[builder] sha256: e3b0c44298fc...
[builder] wrote: infra/inference/artefact/episode_detail.json
```

## 步驟 3：byte-identical reproducibility 驗證

```bash
sha256sum infra/inference/artefact/episode_detail.json > /tmp/sha-1.txt
python scripts/build_episode_artifact.py \
    --run-dir runs/20260506_004455_659b8eb_seed42 \
    --data-root data/raw \
    --output infra/inference/artefact/episode_detail.json
sha256sum infra/inference/artefact/episode_detail.json > /tmp/sha-2.txt
diff /tmp/sha-1.txt /tmp/sha-2.txt && echo "BYTE-IDENTICAL OK"
```

預期：`BYTE-IDENTICAL OK`（憲法 Principle I gate）。

## 步驟 4：build + 啟動完整 stack

```bash
docker compose -f docker-compose.yml -f infra/docker-compose.gateway.yml up --build -d
```

預期 005 startup log 含：
```
[inference] EpisodeStore: loaded 1 episode from /app/episode_detail.json
[inference] EpisodeStore: episode id=20260506_004455_659b8eb_seed42, frames=330, assets=6
```

005 缺 artefact 時應 fail fast：
```
[inference] FATAL: EPISODE_ARTEFACT_PATH=/app/episode_detail.json not found
```
container exit code 非零（驗收 SC-005）。

## 步驟 5：curl 驗證 API

```bash
# 列表
curl -s http://localhost:8080/api/v1/episodes | jq .
```
預期：
```json
{
  "items": [
    {
      "id": "20260506_004455_659b8eb_seed42",
      "policyId": "ppo-smc-v1",
      "startDate": "2025-01-02",
      "endDate": "2026-04-28",
      "nSteps": 329,
      "finalNav": 1.7292,
      "sharpeRatio": 1.7264,
      "maxDrawdownPct": 15.73,
      ...
    }
  ],
  "meta": { "count": 1, "generatedAt": "2026-05-07T..." }
}
```

```bash
# 詳情
curl -s http://localhost:8080/api/v1/episodes/20260506_004455_659b8eb_seed42 | jq '.data.trajectoryInline | length'
```
預期：`330`（含 step=0）。

```bash
# 404
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/episodes/does-not-exist
```
預期：`404`。

## 步驟 6：前端 Overview 頁

```bash
# warroom 已透過 compose 啟在 5173；或本機 dev：
cd apps/warroom && pnpm dev
```

開瀏覽器 `http://localhost:5173/#/overview`，預期：
- KPI bar 顯示 Final NAV 1.7292、Sharpe 1.7264、MDD 15.73%
- NAV+drawdown 折線
- 權重 stacked area
- 6 個資產 K-line + SMC overlay
- SMC events 列表（BOS / CHoCh / FVG / OB）
- Reward sidebar（cumulative + per-step）

對應 SC-001。

## 故障排解

| 症狀 | 原因 | 解法 |
|---|---|---|
| 005 啟動 immediate exit | artefact 缺檔 | 重跑步驟 1–2 |
| `GET /api/v1/episodes` 回 500 | EpisodeStore load 失敗 | 看 005 stderr，多半 schema validation fail |
| 兩次 sha256 不同 | float repr / dict 順序 / NaN | 檢查 builder 是否漏 `sort_keys=True` 或漏 round |
| Overview KPI 顯示 0 | mapper schema 不對齊 | 跑 `pnpm test apps/warroom`，看 mapper unit test |
| gateway 504 | 005 lifespan 還沒完成 | 等 005 healthcheck 綠後再打 gateway |
