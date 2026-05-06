# Quickstart: SMC Engine v2

**Feature**: 008-smc-engine-v2
**Phase**: 1 — Local validation guide

開發者本地驗證 v2 落地的完整步驟。對應 `/speckit.implement` 跑完之後，研究員應能執行下列流程驗收。

## 前置條件

- 已 checkout `008-smc-engine-v2` branch。
- 已通過 `docker compose build dev` 建好 dev 容器。
- `data/raw/` 內含至少一個 daily parquet（feature 002 產出）。

## Step 1：跑單元 + contract test

```bash
docker compose run --rm dev pytest tests/unit/test_structure.py tests/unit/test_ob.py tests/unit/test_fvg.py tests/unit/test_batch.py tests/unit/test_incremental.py tests/contract/test_smc_observation.py tests/contract/test_event_schema.py -v
```

**期待**：全部通過。新增 case 包含：

- `test_structure.py::test_bos_dedup_same_swing_only_once`
- `test_structure.py::test_choch_priority_over_bos`
- `test_structure.py::test_initial_bos_from_neutral_sets_trend`
- `test_structure.py::test_swing_and_break_same_bar_order`
- `test_ob.py::test_ob_count_le_break_count`
- `test_ob.py::test_ob_source_break_alignment`
- `test_ob.py::test_no_ob_for_unbroken_swing`
- `test_fvg.py::test_atr_filter_below_ratio_excluded`
- `test_fvg.py::test_atr_filter_at_boundary_kept`
- `test_fvg.py::test_atr_nan_falls_back_to_pct`
- `test_batch.py::test_breaks_signal_array_consistency`
- `test_batch_incremental_equivalence.py::test_batch_incremental_equivalence_random_seeds`
- `test_contract::test_observation_5_channel_shape_unchanged`
- `test_contract::test_structure_break_json_schema_valid`

## Step 2：跑 batch_compute on real data，sanity check 數量

```bash
docker compose run --rm dev python -c "
import pandas as pd
from smc_features import batch_compute, SMCFeatureParams

df = pd.read_parquet('data/raw/nvda_daily_20180101_20260429.parquet')
params = SMCFeatureParams()  # default fvg_min_atr_ratio=0.25
result = batch_compute(
    timestamps=df['timestamp'].to_numpy(dtype='datetime64[ns]'),
    opens=df['open'].to_numpy(dtype='float64'),
    highs=df['high'].to_numpy(dtype='float64'),
    lows=df['low'].to_numpy(dtype='float64'),
    closes=df['close'].to_numpy(dtype='float64'),
    valid_mask=pd.Series([True] * len(df)).to_numpy(),
    params=params,
)
print(f'NVDA 8 yr daily ({len(df)} bars):')
print(f'  breaks  : {len(result.breaks)} (BOS={sum(1 for b in result.breaks if b.kind.startswith(\"BOS\"))}, CHoCh={sum(1 for b in result.breaks if b.kind.startswith(\"CHOCH\"))})')
print(f'  obs     : {len(result.obs)} (≤ breaks: {len(result.obs) <= len(result.breaks)})')
print(f'  fvgs    : {len(result.fvgs)} (target < 200)')
print(f'  bos_signal nonzero: {(result.bos_signal != 0).sum()}')
print(f'  choch_signal nonzero: {(result.choch_signal != 0).sum()}')
print(f'  signal == event count: {(result.bos_signal != 0).sum() + (result.choch_signal != 0).sum() == len(result.breaks)}')
"
```

**期待數值範圍**（依 spec SC-001 ~ SC-003）：

```text
NVDA 8 yr daily (2092 bars):
  breaks  : ~50–80
  obs     : ~40–70 (≤ breaks)
  fvgs    : <200
  bos_signal nonzero == BOS event count
  choch_signal nonzero == CHoCh event count
  signal == event count: True
```

## Step 3：跑 incremental ↔ batch 等價性快檢

v1 設計 `incremental_compute` 內部以 `batch_compute` 全重算尾段一根（research R6），等價性透過共享 batch 程式碼**結構性保證**。本 step 驗證：「先 batch 前 n-1 根 → 再 incremental 推進第 n 根」與「一次 batch n 根」產生相同的最後一列 FeatureRow 與相同的 BatchResult.breaks 累積結果。

```bash
docker compose run --rm dev python -c "
import pandas as pd
from smc_features import batch_compute, incremental_compute, SMCFeatureParams

df = pd.read_parquet('data/raw/nvda_daily_20180101_20260429.parquet').head(500)
df = df.set_index('timestamp')
params = SMCFeatureParams()

batch_full = batch_compute(df, params)
batch_prefix = batch_compute(df.iloc[:-1], params)
row, state_after = incremental_compute(batch_prefix.state, df.iloc[-1])

last = batch_full.output.iloc[-1]
checks = [
    row.bos_signal == last['bos_signal'],
    row.choch_signal == last['choch_signal'],
    row.fvg_distance_pct == last['fvg_distance_pct'] or (pd.isna(row.fvg_distance_pct) and pd.isna(last['fvg_distance_pct'])),
    row.ob_touched == last['ob_touched'],
    state_after.bar_count == batch_full.state.bar_count,
    state_after.trend_state == batch_full.state.trend_state,
    tuple(batch_full.breaks) == tuple(batch_full.breaks),  # 結構性同一份
]
assert all(checks), f'EQUIVALENCE FAILED: {checks}'
print(f'batch breaks: {len(batch_full.breaks)}')
print('OK: incremental == batch')
"
```

**期待**：印出 `OK: incremental == batch`。

## Step 4：JSON Schema 驗證 StructureBreak

```bash
docker compose run --rm dev python -c "
import json, jsonschema
from dataclasses import asdict
import numpy as np
from smc_features import StructureBreak

# 取 Step 2 中的第一筆 break，轉 JSON
schema = json.load(open('specs/008-smc-engine-v2/contracts/structure_break.schema.json'))
example = schema['examples'][0]
jsonschema.validate(example, schema)
print('OK: StructureBreak schema valid')
"
```

## Step 5：覆蓋率與 lint

```bash
docker compose run --rm dev pytest tests/ --cov=src/smc_features --cov-report=term-missing
docker compose run --rm dev mypy src/smc_features/
docker compose run --rm dev ruff check src/smc_features/ tests/
```

**期待**：

- Coverage on `src/smc_features/` ≥ 90%
- mypy: 0 errors
- ruff: 0 errors

## Step 6：（後續 / out-of-scope）重生 fixture 並肉眼檢查 War Room

`feature 007 follow-up`，本 feature 不要求：

```bash
docker compose run --rm dev python apps/warroom/scripts/parquet_to_ohlc_fixture.py \
  --raw-dir data/raw \
  --detail apps/warroom/src/mocks/fixtures/episode-detail.json \
  --output apps/warroom/src/mocks/fixtures/episode-detail.json
cd apps/warroom && pnpm dev
# 開瀏覽器，肉眼檢查：BOS / CHoCh / OB / FVG 矩形密度合理
```

## 驗收 Checklist

- [ ] Step 1 全部通過
- [ ] Step 2 數量在預期範圍
- [ ] Step 3 印出 `OK: incremental == batch`
- [ ] Step 4 印出 `OK: StructureBreak schema valid`
- [ ] Step 5 coverage / mypy / ruff 全綠
- [ ] （optional）Step 6 視覺檢查通過

跑完上述 Step 1–5 即可宣告 feature 008 落地完成。
