# Quickstart: 001-smc-feature-engine

**Date**: 2026-04-29
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Contracts**: [contracts/api.pyi](./contracts/api.pyi)

目標：讓新成員在 **5 分鐘內**完成「讀取 002 快照 → 計算 SMC 特徵 → 視覺化 → 跑測試」。

---

## 0. 前置條件

- Python 3.11 或 3.12（CI 同時驗證兩版本）
- 已 `git clone` 本 repo 並停留於本 feature 對應 commit
- Feature 002 的 Parquet 快照已存在於 `data/raw/`（若無，先依 002 quickstart 執行抓取或從 repo checkout 已 commit 的快照）

---

## 1. 安裝相依套件

```bash
# 從 repo 根目錄
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell 改為 .venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt # 完全鎖版本，保證跨環境可重現（research R7）
pip install -e .                      # 將 src/smc_features/ 安裝為可匯入套件
```

驗證：

```bash
python -c "import smc_features; print(smc_features.__version__)"
```

---

## 2. 批次計算（Batch Mode）

```python
from pathlib import Path
import pandas as pd
from smc_features import SMCFeatureParams, batch_compute

# 2.1 讀取 feature 002 的快照（已含 quality_flag 欄位）
snapshot = Path("data/raw/nvda_daily_20180101_20260429.parquet")
df = pd.read_parquet(snapshot)

# 2.2 設定特徵參數（預設值來自 research.md R1–R3）
params = SMCFeatureParams(
    swing_length=5,
    fvg_min_pct=0.001,
    ob_lookback_bars=50,
    atr_window=14,
)

# 2.3 計算特徵；include_aux=True 會多輸出視覺化所需欄位
result = batch_compute(df, params, include_aux=True)

print(result.output.tail())      # bos_signal、choch_signal、fvg_distance_pct、ob_touched、ob_distance_ratio
print(result.state.bar_count)    # 已處理 K 棒總數
```

預期：

- `result.output` 列數與 `df` 完全相同（spec FR-001）。
- `quality_flag != "ok"` 列的特徵欄位皆為 `NaN` / `pd.NA`（spec FR-014）。
- 兩年 NVDA 日線（約 500 列）執行時間 < 30 秒（SC-001）。

---

## 3. 視覺化

```python
from smc_features import visualize

# 3.1 PNG（mplfinance，靜態，適合論文圖）
visualize(
    result.output,
    time_range=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-30")),
    output_path="reports/nvda_2024H1.png",
    fmt="png",
    params=params,
)

# 3.2 HTML（plotly，互動，適合戰情室嵌入）
visualize(
    result.output,
    time_range=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-30")),
    output_path="reports/nvda_2024H1.html",
    fmt="html",
    params=params,
)
```

打開 `reports/nvda_2024H1.png` 後肉眼覆核：
- swing high/low 標記是否落在轉折處
- FVG 帶（淡色矩形）是否覆蓋三 K 棒缺口
- OB 帶與 BOS/CHoCh 文字標籤是否與結構斷裂位置吻合

此步驟對應憲法 Principle II（特徵可解釋性）的人工驗證關卡（SC-005）。

---

## 4. 增量計算（Incremental Mode）

模擬「即時來一根新 K 棒」的場景：

```python
from smc_features import incremental_compute

# 4.1 用前 N-1 根批次計算，拿到 state
df_prefix = df.iloc[:-1]
prefix_result = batch_compute(df_prefix, params)

# 4.2 把第 N 根 bar 餵進增量函式
last_bar = df.iloc[-1]            # name 為該 bar 的 pd.Timestamp
new_row, new_state = incremental_compute(prefix_result.state, last_bar)

print(new_row)
```

驗證等價性（spec FR-008，data-model.md invariant 4）：

```python
# new_row 應等於 batch 完整跑一次的最後一列
batch_last = batch_compute(df, params).output.iloc[-1]
assert new_row.bos_signal == batch_last["bos_signal"]
assert new_row.choch_signal == batch_last["choch_signal"]
# 浮點欄位比對使用 atol=1e-9（research R5）
import math
assert math.isclose(new_row.fvg_distance_pct, batch_last["fvg_distance_pct"], abs_tol=1e-9, rel_tol=0)
```

預期單根延遲 < 10 ms（SC-003）。

---

## 5. 跑測試

```bash
# 全部測試 + coverage
pytest --cov=smc_features --cov-report=term-missing

# 只跑契約測試（檢查公開 API 簽章與不變式）
pytest tests/contract/ -v

# 只跑單一 BOS 規則的單元測試
pytest tests/unit/test_bos.py::test_bos_breaks_above_last_swing_high -v
```

通過標準：
- coverage ≥ 90%（plan.md 與憲法 Spec SC-004）
- 所有 contract 測試綠燈
- 7 個不變式測試（data-model.md §9）綠燈

---

## 6. 常見問題

| 症狀 | 原因 | 解法 |
|---|---|---|
| `KeyError: 'quality_flag'` | 002 舊版 Parquet 未含此欄位 | 升級 002 快照；或 `df["quality_flag"] = "ok"` 補上 |
| 輸出全為 NaN | `swing_length` 大於資料長度 | 檢查資料列數 ≥ `2*swing_length+1` |
| 跨平台數值不一致 | NumPy / BLAS 環境差異 | 確認已 `pip install -r requirements-lock.txt`；CI 在三平台跑 atol=1e-9 比對 |
| `visualize` 報缺欄位 | `batch_compute` 未指定 `include_aux=True` | 重跑時加上 `include_aux=True` |

---

## 7. 下一步

- 想看完整不變式檢查清單：`data-model.md §9`
- 想了解判定演算法數學定義：`research.md` R1–R3
- 想擴充參數預設值：修改 `SMCFeatureParams` 並補單元測試（憲法 Principle II）
- 想把這些特徵餵入 PPO：等待後續 feature（PPO 訓練環境 spec）
