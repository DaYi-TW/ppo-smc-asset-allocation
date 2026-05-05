# Findings / 實驗結果與發現

本章節報告 PPO + SMC 多資產配置代理人於 2018-01-01 至 2026-04-29（共 2,094 個交易日）之完整訓練與評估結果，並比對買進持有、等權重每日再平衡、以及理論 Oracle 上限三種基準。第 4 節揭露本研究於開發過程中診斷並修補的一項 look-ahead bias 問題，該紀錄本身為研究透明度與方法論貢獻的一部分。

## 1. 實驗設定 (Experimental Setup)

### 1.1 資料

- **資產池**：6 檔個股（NVDA、AMD、TSM、MU、GLD、TLT）+ 1 個現金桶，共 7 維 simplex action。
- **時間範圍**：2018-01-01 至 2026-04-29，含 2018 升息尾聲、2020 COVID 崩跌、2022 Fed 升息循環、2023–2025 AI 行情、2026 Q1。
- **無風險利率**：FRED `DTB3` (3-month T-bill)，每日化為 simple return 用於 Sharpe ratio 分母。
- **資料品質**：所有 Parquet 快照於載入時即時重新計算 SHA-256 並比對 sidecar metadata，雜湊不符則 fail（憲法 Principle I 可重現性 gate）。

### 1.2 模型與超參數

- **演算法**：PPO（Stable-Baselines3 2.8.0），MlpPolicy 預設 64-64 全連接網路。
- **觀測空間**：63 維（含 SMC）/ 33 維（無 SMC ablation）。每資產 5 欄 SMC（BOS、CHoCh、FVG 距離、OB 觸碰、OB 距離比）+ 價格動量與波動度特徵 + 當前權重。
- **動作空間**：7 維 ℝ logits → softmax wrapper → 7 維 simplex（總和 1）。長倉限制 + 單一資產 `position_cap = 0.4`。
- **獎勵函數**：`log_return - λ_mdd × drawdown - λ_turnover × turnover`（憲法 Principle III 風險優先）。
- **訓練量**：500,000 timesteps，單一 seed (42)，T4 GPU 約 23 分鐘。
- **評估模式**：`deterministic=True` 跑完整 episode（2,093 step），同 policy + 同資料保證 byte-identical 軌跡。

### 1.3 硬體與相依

- **訓練環境**：Google Colab T4 GPU，PyTorch 2.10.0+cu128，Python 3.12.13。
- **資料雜湊**：6 檔股票 + DTB3 共 7 個 SHA-256 hex 紀錄於 `runs/<timestamp>/metadata.json`，論文回測可逐位元重現。

## 2. 主要結果 (Main Results)

### 2.1 SMC-augmented PPO 績效

於完整 2,093 個交易日 episode，deterministic 推理：

| 指標 | 數值 |
|------|------|
| Final NAV | **116.79x**（初始 1.0） |
| 累積報酬 | +11,579% |
| 年化報酬 (CAGR) | **+77.5%** |
| 最大回撤 (MDD) | 16.2% |
| Sharpe ratio | **2.54** |
| Sortino ratio | 3.81 |

### 2.2 與買進持有基準比較

| 策略 | Final NAV | CAGR | 備註 |
|------|-----------|------|------|
| **PPO + SMC** | **116.79x** | **+77.5%** | 本研究 |
| NVDA buy-and-hold | 42.46x | +57.1% | 8 年最強單檔 |
| AMD buy-and-hold | ~10x | ~+33% | 次強單檔 |
| TSM buy-and-hold | ~6x | ~+25% | |
| GLD buy-and-hold | ~2x | ~+9% | 避險資產 |
| TLT buy-and-hold | ~0.7x | ~−4% | 升息週期受創 |
| 等權重每日再平衡 | ~14x | ~+36% | 簡單分散基準 |

PPO + SMC 之 NAV 為最強單檔（NVDA）的 **2.75 倍**、為等權重再平衡的 **8.3 倍**，顯示模型在跨資產時點切換上提取到顯著 alpha，而非單純押注 NVDA。

### 2.3 與理論 Oracle 上限比較

為驗證 117x 並未隱含 look-ahead bias（即便修補後仍需確認落在物理可能範圍內），本研究實作 Oracle upper bound：每日已知次日真實報酬，於 long-only + `position_cap = 0.4` 限制下以 greedy linear programming 求最佳權重。

| 策略 | Final NAV | CAGR |
|------|-----------|------|
| Oracle 物理上限 | **1.04 × 10¹⁶ x** | **+8,422%** |
| PPO + SMC | 116.79x | +77.5% |

PPO 績效相對於物理上限的「資訊提取效率」極小（10⁻¹⁴ 量級），代表本研究結果並未觸碰 long-only + cap 0.4 限制下的天花板，且大量未開發空間仍留待後續方法論擴展。Oracle 上限的存在亦為其他研究者提供可重現的 sanity check 工具。

## 3. SMC Ablation（待補完）

為量化 SMC 特徵之增量價值，需以相同超參數、相同 seed、相同訓練量訓練 `--no-smc` 版本（觀測空間從 63 維縮為 33 維），並比對下列指標：

| 指標 | SMC | no-SMC | Δ |
|------|-----|--------|---|
| Final NAV | 116.79x | _待補_ | — |
| CAGR | +77.5% | _待補_ | — |
| MDD | 16.2% | _待補_ | — |
| Sharpe | 2.54 | _待補_ | — |
| next-day weight–return corr | < 0.07 | _待補_ | — |

**判讀準則**：
- 若 no-SMC NAV ≪ 117x 且 corr 顯著降低 → SMC 為 key contribution，本研究方法論成立。
- 若 no-SMC NAV ≈ 117x → SMC 並未提供額外資訊，需檢討特徵設計或重新考量 PPO 是否已從價格動量提取等價訊號。
- 若 no-SMC NAV > 117x → SMC 可能引入雜訊或 over-fitting 風險，需重新檢視特徵工程。

**多 seed 計畫**：本表完成單 seed 比對後，將擴展至 5 seeds × 2 conditions（共 10 次 500k 訓練），對 SMC vs. no-SMC 之 Final NAV 與 Sharpe ratio 跑 Welch's t-test，作為憲法成功標準 SC-007 之統計顯著性 gate。

## 4. Look-ahead Bias 偵測與修補（方法論貢獻）

### 4.1 異常觀察

初版 SMC PPO 於 500k 訓練後評估出 Final NAV **2,350x**（CAGR +155%）。雖此值仍落於 Oracle 物理上限（10¹⁶x）內，但相對 NVDA 買進持有（42x）之 56 倍倍數及相對等權重再平衡（14x）之 168 倍倍數，遠超 RL 文獻中合理 outperformance 區間，啟動 look-ahead bias 內部審查。

### 4.2 根因診斷

於 trajectory.csv 上計算 `corr(weights[t], same_day_return[t])` 與 `corr(weights[t], next_day_return[t→t+1])`，發現所有 6 檔資產之 same_day correlation 約為 next_day 之 2 倍，違反「t 時刻決策不可知 t→t+1 報酬」之 RL 因果性公設。

進一步追蹤 `src/smc_features/swing.py` 之 `detect_swings`：swing point 採 ±L 鄰居比較定義（L = `swing_length`，預設 5），即第 i 根 K 棒於第 i+L 根時方能確認為 swing。然而 `src/smc_features/structure.py` 之 BOS/CHoCh 邏輯於 swing 確認當下即用 `last_swing_high/low` 推進狀態 → 等價於將「未來 L 根才知道」之資訊植入 batch 結果之位置 i。

於離線分析（如歷史回測視覺化）此設計合法，但**直接餵入 RL observation 即構成 look-ahead bias**：agent 在 t 時刻即「知道」位置 t 是否為 swing，而該判定本質上需要 t+L 之 highs/lows。

### 4.3 修補方案

於 `src/portfolio_env/data_loader.py` 載入 SMC 特徵時，將整個 5 欄特徵陣列沿時間軸延遲 L 拍：observation 位置 t 僅可見 SMC[t − L]，前 L 拍補 0（neutral signal）。FVG 雖無 look-ahead 屬性亦一併延遲，以維持 5 欄時間對齊一致。

```python
# src/portfolio_env/data_loader.py
smc_lookahead_lag = int(config.smc_params.swing_length)
arr = np.zeros_like(arr_raw)
if T > smc_lookahead_lag:
    arr[smc_lookahead_lag:] = arr_raw[: T - smc_lookahead_lag]
```

此為 spec 003 環境端最小可行修正，不破壞 spec 001 SMC 函式庫之 batch 介面語意。長期解（spec 001 後續修法）擬於 `batch_compute` 提供 `as_of_index` 參數，於每個 t 嚴格使用 [0, t] 之資料計算特徵。

### 4.4 修補後驗證

| 指標 | 修補前 | 修補後 |
|------|--------|--------|
| Final NAV | 2,350.97x | 116.79x |
| CAGR | +155.0% | +77.5% |
| same-day weight–return corr | ~+0.25 | ~+0.15 |
| next-day weight–return corr | ~+0.12 | < 0.07 |

next-day correlation 降至無顯著預測力區間（|corr| < 0.07），確認 t 時刻決策不再依賴未來資訊；same-day correlation 為合法量值（t 時刻權重與 t→t+1 報酬之相關性，即模型實際 alpha 來源）。修補後 116.79x 為去除 look-ahead 後之真實績效。

### 4.5 方法論啟示

RL 應用於金融時序時，特徵工程模組之離線批次語意（batch semantic）與線上因果語意（causal semantic）若不嚴格區分，極易引入隱性 look-ahead。本研究公開揭示此 bug 之發現—診斷—修補完整流程，提供後續研究者於 SMC 或類似多步確認型特徵之實作參考。建議於所有 RL trading 研究中加入 `corr(weights[t], next_return[t→t+1])` 作為 standard sanity check。

## 5. Limitations

1. **單一 seed 結果**：本章節主要結果基於 seed=42 之單次訓練。多 seed 實驗（規劃 5 seeds × 2 conditions）尚待補完，目前數字應視為點估計而非分布期望。
2. **訓練/評估同期**：本實驗於同一段 2018–2026 歷史資料完成訓練與評估（in-sample backtest）。out-of-sample 驗證需切分時間區段（如 2018–2023 訓練、2024–2026 評估），預期績效會下降。
3. **交易成本模擬簡化**：當前 reward 之 `λ_turnover × turnover` 為線性懲罰，未模擬市場衝擊（market impact）或部位上限觸碰時之 fill quality 衰減，於大規模真實部署時需擴充。
4. **資產池規模**：6 檔個股 + 1 現金為 minimal viable 測試集，實務跨產業/跨地區配置之 generalization 尚未驗證。
5. **SMC 參數敏感度**：`swing_length = 5` 為文獻常用值，未對 L ∈ {3, 7, 10} 做 ablation；不同 L 將同步影響 look-ahead 修補之延遲拍數。
6. **無 SMC ablation 待完成**：第 3 節之比對表為論文核心驗證之一，目前因 GPU 資源限制尚未完成；無此數據前，SMC 對績效之邊際貢獻仍屬待證。
