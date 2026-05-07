# Data Model: PPO Episode Detail Store

**Feature**: 009-episode-detail-store
**Date**: 2026-05-07

## 1. EpisodeArtefact

整份 episode 的單一檔案表示；序列化為 JSON。

```text
EpisodeArtefact = EpisodeDetail   # 即頂層為 EpisodeDetail，artefact 即 detail JSON
```

artefact 落地路徑：`runs/<run_id>/eval_oos/episode_detail.json`，build-time 複製到 `infra/inference/artefact/episode_detail.json`。

## 2. EpisodeSummary

對應 `apps/warroom/src/viewmodels/episode.ts` 的 `EpisodeSummaryViewModel`。

| Field | Type | Source | Constraint |
|---|---|---|---|
| `id` | string | `<run_id>` | unique；MVP 只有一筆 |
| `policyId` | string | run metadata | 對齊 005 policies endpoint |
| `startDate` | string (ISO date) | trajectory 第 1 frame | YYYY-MM-DD |
| `endDate` | string (ISO date) | trajectory 末 frame | YYYY-MM-DD |
| `nSteps` | integer | eval_summary | == trajectory length − 1（含初始 frame） |
| `initialNav` | float | eval_summary | 通常 1.0 |
| `finalNav` | float | eval_summary | round(x, 12) |
| `cumulativeReturnPct` | float | eval_summary | (finalNav − 1) × 100 |
| `annualizedReturnPct` | float | eval_summary | round(x, 12) |
| `maxDrawdownPct` | float | eval_summary | ≥ 0 |
| `sharpeRatio` | float | eval_summary | round(x, 12) |
| `sortinoRatio` | float | eval_summary | round(x, 12) |
| `includeSmc` | boolean | eval_summary | true（OOS run 都帶 SMC） |

## 3. EpisodeDetail

對應 viewmodels `EpisodeDetailViewModel`。Detail = Summary + 4 個大陣列。

| Field | Type | Description |
|---|---|---|
| `summary` | EpisodeSummary | 上節 |
| `trajectoryInline` | TrajectoryFrame[] | 長度 nSteps + 1（含 step=0 初始 frame） |
| `rewardBreakdown` | RewardSeries | byStep + cumulative |
| `smcOverlayByAsset` | Record<assetCode, SMCOverlay> | 6 個 key |
| `meta` | EpisodeDetailMeta | 生成資訊 |

### EpisodeDetailMeta

| Field | Type | Description |
|---|---|---|
| `generatedAt` | string (ISO datetime UTC) | builder 執行時間（**注意**：Principle I 要求 byte-identical → 此欄位不參與 sha256；序列化時放在獨立區塊，artefact byte-identical hash 算 trajectoryInline + rewardBreakdown + smcOverlayByAsset 三者） |
| `evaluatorVersion` | string | 例如 "ppo-smc-evaluator-0.4.0" |
| `policyChecksum` | string | sha256 of policy.zip |
| `dataChecksum` | string | sha256 of data/raw 整目錄 |

## 4. TrajectoryFrame

對應 `viewmodels/trajectory.ts` 的 `TrajectoryFrame`。

| Field | Type | Constraint |
|---|---|---|
| `timestamp` | string (ISO date) | YYYY-MM-DD |
| `step` | integer | 0..nSteps |
| `weights` | WeightAllocation | 見 §5 |
| `nav` | float | round(x, 12) |
| `drawdownPct` | float | (peak − nav) / peak × 100；≥ 0 |
| `reward` | RewardSnapshot | 見 §6；step=0 時全 0 |
| `smcSignals` | SMCSignals | 見 §7 |
| `ohlcv` | OHLCV | 預設資產（NVDA），向後相容 |
| `ohlcvByAsset` | Record<assetCode, OHLCV> | 6 個 key；缺值不允許 |
| `action` | ActionVector | 見 §8；step=0 時 raw / normalized 為初始 weights，logProb / entropy = 0 |

## 5. WeightAllocation

| Field | Type | Constraint |
|---|---|---|
| `riskOn` | float | NVDA + AMD + TSM + MU |
| `riskOff` | float | GLD + TLT |
| `cash` | float | CASH |
| `perAsset` | Record<string, float> | 7 個 key（含 CASH）；total ≈ 1（1e-6 容差） |

**Invariant**：`riskOn + riskOff + cash ∈ [1 − 1e-6, 1 + 1e-6]`；`perAsset[NVDA..MU].sum() ≈ riskOn`；`perAsset[GLD,TLT].sum() ≈ riskOff`；`perAsset[CASH] ≈ cash`。

## 6. RewardSnapshot

| Field | Type | Constraint |
|---|---|---|
| `total` | float | round(x, 12) |
| `returnComponent` | float | round(x, 12) |
| `drawdownPenalty` | float | ≥ 0；round(x, 12)（顯示時 UI 加負號） |
| `costPenalty` | float | ≥ 0；round(x, 12) |

**Invariant**：`abs(total − (returnComponent − drawdownPenalty − costPenalty)) ≤ 1e-9`。

### RewardSeries

| Field | Type | Description |
|---|---|---|
| `byStep` | RewardSnapshot[] | 長度 == nSteps（不含 step=0） |
| `cumulative` | RewardCumulativePoint[] | 長度 == nSteps |

### RewardCumulativePoint

| Field | Type |
|---|---|
| `step` | integer |
| `cumulativeTotal` | float |
| `cumulativeReturn` | float |
| `cumulativeDrawdownPenalty` | float |
| `cumulativeCostPenalty` | float |

## 7. SMCSignals (per frame)

| Field | Type | Constraint |
|---|---|---|
| `bos` | -1 \| 0 \| 1 | int |
| `choch` | -1 \| 0 \| 1 | int |
| `fvgDistancePct` | float \| null | 無 FVG 時為 null（JSON），不允許 NaN |
| `obTouching` | boolean | |
| `obDistanceRatio` | float \| null | 無 OB 時為 null |

## 8. ActionVector

| Field | Type | Constraint |
|---|---|---|
| `raw` | float[] | length 7（pre-softmax） |
| `normalized` | float[] | length 7（post-softmax，simplex；sum ≈ 1） |
| `logProb` | float | round(x, 12) |
| `entropy` | float | round(x, 12) |

## 9. OHLCV

| Field | Type | Constraint |
|---|---|---|
| `open` | float | > 0 |
| `high` | float | ≥ open, ≥ low, ≥ close |
| `low` | float | ≤ open, ≤ high, ≤ close |
| `close` | float | > 0 |
| `volume` | float | ≥ 0 |

## 10. SMCOverlay (per asset)

對應 `viewmodels/smc.ts` 的 `SMCOverlay`。由 008 SMC engine batch 計算。

| Field | Type |
|---|---|
| `swings` | SwingPoint[] |
| `zigzag` | SwingPoint[] |
| `fvgs` | FVGZone[] |
| `obs` | OBZone[] |
| `breaks` | StructureBreak[] |

各子型態定義見 `viewmodels/smc.ts`（time / price / direction / kind / from / to 等欄位）。

## 11. trajectory.parquet schema（中間產物）

| Column | Parquet dtype | Source |
|---|---|---|
| `date` | string | env trading day |
| `step` | int32 | |
| `nav` | float64 | env info |
| `log_return` | float64 | reward components |
| `weight_NVDA, weight_AMD, weight_TSM, weight_MU, weight_GLD, weight_TLT, weight_CASH` | float64 × 7 | env info |
| `reward_total, reward_return, reward_drawdown_penalty, reward_cost_penalty` | float64 × 4 | env info reward_components |
| `action_raw_0..6` | float64 × 7 | predict 前 obs |
| `action_normalized_0..6` | float64 × 7 | predict 後 wrapper output |
| `action_log_prob, action_entropy` | float64 × 2 | model.policy |
| `smc_bos, smc_choch` | int8 × 2 | env info smc_signals |
| `smc_fvg_distance_pct, smc_ob_distance_ratio` | float64 × 2（nullable） | env info smc_signals |
| `smc_ob_touching` | bool | env info smc_signals |
| `ohlc_NVDA_open, ohlc_NVDA_high, ohlc_NVDA_low, ohlc_NVDA_close, ohlc_NVDA_volume` 等 6 × 5 = 30 columns | float64 × 30 | data/raw OHLC parquet（builder 端 join，evaluator 端可省略 OHLC，由 builder 從 data/raw 讀） |

實際 evaluator 寫的 parquet **不含** OHLC 欄位（僅 close 已可從 data/raw 直接 join）；OHLC join 由 builder 端做。這樣 evaluator 端 parquet 約 70 columns × 329 rows ≈ 0.3 MB。

## 12. legacy CSV schema（向後相容）

```
date, nav, log_return, w_NVDA, w_AMD, w_TSM, w_MU, w_GLD, w_TLT, w_CASH, close_NVDA, close_AMD, close_TSM, close_MU, close_GLD, close_TLT
```

不含 reward / action / smc / OHL+volume；既有 Colab notebook 不破。

## 13. State transitions

| Source | Trigger | Output |
|---|---|---|
| trained policy.zip + data/raw parquet | `python -m ppo_training.evaluate --save-trajectory` | `runs/<run_id>/eval_oos/trajectory.parquet` + `trajectory.csv` + `eval_summary.json` |
| trajectory.parquet + eval_summary.json + data/raw OHLC parquet | `python scripts/build_episode_artifact.py` | `runs/<run_id>/eval_oos/episode_detail.json` + sha256 console output |
| episode_detail.json | `docker build inf` | image with artefact at `/app/episode_detail.json` |
| image with artefact | `docker compose up` → 005 lifespan | in-memory `EpisodeStore` with summary + detail |
| `EpisodeStore` | HTTP GET /api/v1/episodes | envelope `{ items, meta }` |
| `EpisodeStore` | HTTP GET /api/v1/episodes/{id} | envelope `{ data, meta }` 或 404 |

## 14. Validation rules

- Schema 對齊：artefact builder 序列化前用 pydantic `EpisodeDetail` 驗證；任何欄位缺漏 → builder 失敗（fail fast）。
- Reward invariant：每 frame 在 builder 內驗證 `total ≈ return − drawdown − cost`（1e-9 容差）；違反 → builder 失敗。
- Weight invariant：`sum(perAsset) ∈ [0.999999, 1.000001]`；違反 → builder 失敗。
- 005 EpisodeStore 載入時用同一 pydantic 模型驗證；schema 不符 → lifespan 失敗（fail fast，符合 FR-012 / SC-005）。
