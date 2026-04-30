# smc_features — Smart Money Concepts 量化特徵函式庫

純 Python 函式庫，將 SMC（Smart Money Concepts）市場結構概念量化為 PPO 訓練可消費的觀測特徵：BOS / CHoCh / FVG / OB。對應 spec [`001-smc-feature-engine`](../../specs/001-smc-feature-engine/spec.md)。

## 用途

- 餵給強化學習觀測空間的特徵向量（離散結構訊號 + 連續距離比）
- 同時支援「批次計算整段歷史」與「增量推進單根新 K 棒」兩條等價路徑（spec FR-008）
- 跨平台 byte-identical 浮點輸出（憲法 Principle I + spec SC-002）

## 公開 API

```python
from smc_features import (
    batch_compute,         # 一次計算整段
    incremental_compute,   # 推進一根 K 棒
    visualize,             # PNG / HTML 圖層繪製
    SMCFeatureParams,      # 特徵參數
    SMCEngineState,        # 增量狀態
    BatchResult,
    FeatureRow,
    SwingPoint, FVG, OrderBlock,
)
```

簽章與型別契約：[`specs/001-smc-feature-engine/contracts/api.pyi`](../../specs/001-smc-feature-engine/contracts/api.pyi)。

## 上手

完整 5 分鐘教學：[`specs/001-smc-feature-engine/quickstart.md`](../../specs/001-smc-feature-engine/quickstart.md)。

最小範例（doctest 已驗證）：

```python
import pandas as pd
from smc_features import batch_compute, SMCFeatureParams

df = pd.read_parquet("data/raw/nvda_daily_20180101_20260429.parquet")
br = batch_compute(df, SMCFeatureParams())
print(br.output[["bos_signal", "choch_signal", "fvg_distance_pct", "ob_touched"]].tail())
```

## 設計原則

- **frozen dataclass**：所有狀態與參數不可就地修改；違反拋 `dataclasses.FrozenInstanceError`
- **valid_mask 全程貫徹**：`quality_flag != "ok"` 的列特徵全 NaN，且不污染下游視窗（invariant 6）
- **CHoCh 優先於 BOS**：同根 K 棒同時觸發時 `bos_signal == 0 AND choch_signal != 0`（spec FR-019）
- **純函式庫合規**：不得 import Web 框架 / 訊息中介 / 資料庫驅動（spec FR-016；ruff TID251 強制）

## 測試與覆蓋率

```bash
docker compose run --rm dev pytest tests/ --cov=src/smc_features
```

覆蓋率門檻 ≥ 90%（spec SC-004）。
