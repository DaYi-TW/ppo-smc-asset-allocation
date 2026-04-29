# Phase 0 Research: 003-ppo-training-env

**Status**: Complete
**Date**: 2026-04-29
**Plan**: [plan.md](./plan.md)

本檔案蒐集 plan.md 提到的技術未知數，並就每個決策點記錄「Decision / Rationale /
Alternatives considered」。所有決策皆已落實於 plan.md 的 Technical Context 與
Constitution Check 章節，後續 Phase 1 設計與 Phase 2 任務拆解須與本檔對齊。

---

## R1 — `reset(seed=N)` 的四層 seed 同步策略

**Decision**: 在 `PortfolioEnv.reset(seed)` 中，依序執行下列四步，**不依賴任何
全域 `np.random.seed`**：

1. `super().reset(seed=seed)` — 觸發 `gymnasium.Env` 內建 PRNG 初始化（產出
   `self.np_random: numpy.random.Generator`）。
2. `self._py_random = random.Random(seed)` — 環境內部如有 Python 標準函式庫
   `random` 用途，使用此本地實例。
3. `self._numpy_rng = np.random.default_rng(seed)` — 任何 numpy 隨機抽樣
   （例如未來新增的滾動視窗起點抽樣）一律走此 Generator，**不**走 `np.random.*`
   全域介面。
4. 環境內部所有資料切片邏輯（如 `start_date` 隨機化、ablation 抽樣）MUST 以
   `self._numpy_rng` 為唯一隨機源；不從系統時間、不從 `os.urandom`。

**Rationale**：Gymnasium 0.29+ 已將 `np_random` 私有化為環境屬性，但子類別常
忽略「Python `random` 與 numpy 全域 PRNG」這兩條外洩通道。四層全部用本地實例
封裝後，`reset(seed=42)` 兩次得到相同 trajectory（SC-005）成立的前提才存在。

**Alternatives considered**：
- **只用 `super().reset(seed=seed)`**：不夠，環境若呼叫 `np.random.normal(...)`
  會吃到全域 PRNG，破壞可重現性。
- **全域 monkey-patch `np.random.seed(seed)` 於 `__init__`**：違反 Principle I
  的「不依賴全域狀態」精神，且會干擾呼叫方（PPO 訓練 loop）的 PRNG。
- **只用 `np.random.default_rng(seed)` 不呼叫 `super().reset()`**：違反 Gymnasium
  契約，`env_checker.check_env` 會 fail（SC-003 阻擋）。

---

## R2 — 跨平台 byte-identical 算術順序

**Decision**: 環境內所有浮點運算 MUST 遵守固定運算圖，不依賴 numpy 的
broadcasting 順序或 BLAS thread 數：

- **NAV 推進**：`nav_t = nav_{t-1} * dot(weights_{t-1}, returns_t)`，
  `dot` 用 `numpy.dot`（BLAS-backed，但對 7 維小向量等價於純 Python 累加，
  跨平台一致）；returns 預先以 `numpy.float64` 計算。
- **drawdown**：`drawdown_t = max(0.0, (peak_t − nav_t) / peak_t)`，
  `peak_t = max(peak_{t-1}, nav_{t-1})`；先更新 peak、再算 drawdown。
- **turnover**：`turnover_t = 0.5 * sum(abs(w_t − w_{t-1}))`，
  使用 `numpy.abs` + `numpy.sum`（順序固定）。
- **reward 組裝**：`reward = log_return − λ_mdd × drawdown − λ_turnover × turnover`，
  以 Python `−` 運算子按字面順序執行，不用 `numpy.subtract.reduce`。
- **Observation 組裝**：先建立 `numpy.zeros(D, dtype=float32)`，再依 FR-010
  分區寫入，避免 `numpy.concatenate` 的記憶體配置順序差異。

實作層面在 `pyproject.toml` 中 pin `numpy ~= 1.26.x` 並於 CI 設
`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1` 強制單執行緒 BLAS。

**Rationale**：浮點加法不可結合（`(a+b)+c ≠ a+(b+c)` at ULP 級別），多執行緒
BLAS 對 reduction 順序非確定。對 7 維 dot product 來說差異雖然 < 1e-15，但
2090 步累積後可能放大到 1e-9 以上，剛好觸碰 SC-002 容差。鎖單執行緒 + 固定
運算順序是最便宜的解。

**Alternatives considered**：
- **mpmath / decimal 高精度**：過殺；單機效能掉 100x，違反 SC-001 < 30 秒。
- **完全純 Python `math` + `for` 迴圈**：deterministic 但效能不可接受。
- **依賴 `numpy.errstate(over='raise')` 偵錯**：解決不了非結合性問題。

---

## R3 — Reward 權重數值取捨（`λ_mdd=1.0, λ_turnover=0.0015`）

**Decision**: 採用使用者於 `/speckit.specify` 階段選定的 Option B（風控優先型）：
- `λ_mdd = 1.0` — drawdown 與 log return 同數量級。日 log return 典型在
  ±0.02 區間，drawdown 累積可達 0.3 以上；`1.0 × drawdown` 確保大回撤事件
  reward 被顯著扣分（−0.3 級別），驅動 agent 學會風險控制。
- `λ_turnover = 0.0015` — 由 5 bps 滑價（research R4）+ 10 bps 額外懲罰
  合計而成。對單筆完整換手（turnover=1）扣 0.0015 分（≈ 7.5% 的單日典型
  log return σ），抑制過度交易但不至於完全凍結 agent。

**Rationale**：對齊論文 Findings「兼具動態配置與風險控制」主張。若 `λ_mdd=0.1`
（試算的「收益優先型」），drawdown 訊號太弱，agent 退化為趨勢跟隨；若
`λ_mdd=10`，reward 被 drawdown 主導，agent 學會永遠空倉。1.0 是 sweet spot，
與 log return 數量級對齊，便於 PPO 的 advantage normalization 收斂。

**Alternatives considered**：
- **Option A（收益優先型，λ_mdd=0.1, λ_turnover=0.0005）**：不符合憲法
  Principle III「risk-first」字面意義，雖然 PnL 可能更高但偏離研究主張。
- **Option C（學界常見，λ_mdd=0.5, λ_turnover=0.001）**：折衷方案，但
  Option B 的數值可解釋性更強（drawdown 與 log return 1:1 對映）。
- **Sortino-style 下行波動懲罰**：理論優雅但需要滾動視窗計算下行半變異數，
  增加 step 內運算量；MDD 懲罰已涵蓋大部分下行風險訊號。

---

## R4 — 滑價模型與 reward 中交易成本的命名分離

**Decision**: 將「滑價（market microstructure）」與「reward 中的交易成本懲罰」
**概念上與實作上分離**：
- `PortfolioEnvConfig.base_slippage_bps` 預設 5（單邊 bps）— 屬市場模型常數，
  影響 `info["slippage_bps"]` 紀錄與下游回測歸因，**不直接進入 reward 公式**。
- `RewardConfig.lambda_turnover` 預設 0.0015 — reward 中 turnover 項的單一
  係數，已涵蓋 5 bps 滑價的事實成本與額外風險懲罰；agent 只感知這一個數字。

**Rationale**：spec review 中 B2 指出舊設計用 `λ_cost = base_slippage + λ_cost_extra`
合成總係數，但暴露了三個名稱、且 SC-007 ablation 需要設 `λ_cost_extra=−0.0005`
才能歸零，極反直覺。本決策讓 ablation 變成「直接 `λ_turnover=0`」，符合最小
驚訝原則。base_slippage_bps 仍保留是因為下游 backtest（004）可能想分離歸因
「報酬扣除滑價後 vs. 模型訓練感知的 reward」兩條曲線。

**Alternatives considered**：
- **完全移除 base_slippage_bps**：失去歸因能力，下游 backtest 無法回答「滑價
  吃掉多少 alpha」。
- **base_slippage_bps 直接乘進 reward**：回到 B2 的雙重命名問題。

---

## R5 — quality_flag 跳日策略（spec review S1）

**Decision**: 將「跳過該日」與「forward fill」依資料源拆分：

| quality_flag 值 | 來源 | 處理 |
|---|---|---|
| `ok` | 任意 | 正常使用 |
| `missing_close` | 股票 | 跳過該日（從 episode 序列剔除） |
| `zero_volume` | 股票 | 跳過該日 |
| `duplicate_dropped` | 股票 | 跳過該日（保險，002 已去重，但若 metadata 標記則尊重） |
| `missing_rate` | FRED 利率 | 對該日 `risk_free_rate` 欄位做 forward fill；**不**跳日 |

被跳過的日期累積於 `info["skipped_dates"]`（list of ISO date string），於每步
`step()` 之 info 中暴露當前累積值。跳日邏輯於 `__init__` 一次性建立有效
trading day 序列（取「六檔股票全部 quality_flag == ok 的日期」交集），episode
僅 iterate 此序列；FRED missing_rate 只影響該日的 risk-free rate 觀測值，不
影響日序列。

**Rationale**：股票缺值（missing_close、zero_volume）使該日報酬無法定義，必須
跳過；FRED 部分聯邦假日不發布利率屬已知現象，forward fill 是業界慣例（FRED
官方教學亦如此建議），且 risk-free rate 變動緩慢、forward fill 失真極小（< 1 bp）。
此分層讓 spec edge case「資產日曆不對齊」與「quality_flag != ok」兩條規則
不再衝突。

**Alternatives considered**：
- **任一 quality_flag != ok 全部跳日**：太激進，FRED 一年有 ~10 個假日，
  全部跳掉會讓 episode 損失不必要的 step。
- **NaN 報酬該日強制 reward=0、不跳日**：產生人工的「平盤日」，污染 PPO
  學習訊號，違反「不靜默修補」原則。

---

## R6 — Parquet hash 比對時機（spec review S3）

**Decision**: 在 `PortfolioEnv.__init__` 載入每檔資產 Parquet 時，**立即**
重新計算 SHA-256 並與 002 產生的 `*.parquet.meta.json` 比對；不符則 raise
`RuntimeError("Snapshot hash mismatch: {asset} expected {expected_sha}, got
{actual_sha}")` 並中止 `__init__`，環境物件不創建。

`step()` 與 `reset()` **不**重複比對（hash 已在 __init__ 階段確認、檔案
不會在 episode 中變動）。`info["data_hashes"]` 內容於 __init__ 一次組裝後
快取為 dict，每步 step 僅引用同一物件（避免重算）。

**Rationale**：hash 比對是 O(檔案大小) 的成本（~1 MB Parquet 約 5 ms），
每步重算會吃掉 SC-001 budget 的 10% 以上，且場景上沒意義（檔案不會在 episode
中被改）。`__init__` 一次性檢查兼顧 fail-fast 與效能。

**Alternatives considered**：
- **延遲到 step(0) 才比對**：使用者建立 env 物件後若不 step，問題不會浮現，
  違反 fail-fast 原則。
- **完全省略 hash 比對**：違反 FR-021 與憲法 Principle I 的可重現性鏈條。

---

## R7 — SMC 特徵預計算策略

**Decision**: 在 `PortfolioEnv.__init__` 載入完六檔股票 OHLCV 後，**一次性**
呼叫 `smc_features.batch_compute(df, params)` 為每檔股票計算全 episode 的
SMC 特徵欄位（`bos_signal`、`choch_signal`、`fvg_distance_pct`、`ob_touched`、
`ob_distance_ratio`），結果預先轉為 `numpy.ndarray(dtype=float32)` 並切片
為 `self._smc_features: dict[str, np.ndarray]`（key=ticker, value=shape
`(T, 5)`）。`step()` 內僅用 `self._smc_features[ticker][t]` 查表寫入
observation。

預計算結果同步用 fingerprint（hash of `(asset_hash, smc_params_hash)`）作為
cache key，後續若同 commit、同參數、同 seed 重複建立 env 可選擇從 in-memory
cache 復用（屬 nice-to-have，**不**寫入磁碟）。

**Rationale**：SMC 特徵涉及 swing point detection、ATR 滾動、FVG/OB 狀態
追蹤，逐步重算每天成本約 1–5 ms × 2090 step × 6 asset ≈ 60 秒，必爆 SC-001
budget。Batch 預計算將總成本壓到 ~5 秒（一次性），step 內 O(1) 查表。

**Alternatives considered**：
- **每步增量計算（呼叫 001 的 incremental_compute）**：理論上效能可接受，
  但 incremental API 由 001 spec FR-001 定義為「狀態傳遞式」，整合複雜度高
  且容易出 bug；本 feature 訓練場景永遠是 batch 全 episode，沒必要走增量路徑。
- **預計算後寫入磁碟 cache**：違反 FR-005「不直接寫檔」精神，且引入磁碟 IO
  非確定性。

---

## R8 — 容差語意分層（spec review N1）

**Decision**: 全 spec / plan / contracts 範圍內，浮點容差按下列分層：

| 用途 | 容差 | 引用 |
|---|---|---|
| 純算術同機器運算結果驗證（如 reward 三項加總 == reward） | 1e-12 | US2、SC-007 |
| 跨平台 byte-identical（如最終 NAV、reward 序列 MD5） | 1e-9 | FR-020、SC-002、SC-005 |
| `info["reward_components"]` 三項分量加總一致性檢查 | 1e-9 | FR-009、SC-004 |
| Action L1 normalize 觸發門檻 | 1e-6 | FR-014 |

於 quickstart.md 的「常見錯誤」段補一句說明：研究者若看到自家實驗的 reward
重建誤差落在 1e-12 以下、跨機器驗證落在 1e-9 以下即視為通過。

**Rationale**：1e-12 對應 float64 的 ~14 位有效數字（接近 ULP 邊界），適合同
機器同 BLAS thread 環境；1e-9 為 R2 鎖單執行緒後的合理跨平台 budget；1e-6 為
PPO policy head 數值不穩定性的安全餘量（不會誤觸發歸一化）。三個閾值彼此差
3 個量級，避免邊界混淆。

**Alternatives considered**：
- **單一容差 1e-9 全用**：過寬，純算術測試會錯過小於 1e-9 的真實 bug。
- **單一容差 1e-12 全用**：過嚴，跨平台測試在 CI 上會頻繁 false fail。

---

## 決策摘要表（給 plan / tasks 引用）

| 編號 | 主題 | Decision 一句話 |
|---|---|---|
| R1 | reset seed | 四層本地 PRNG，不碰全域 |
| R2 | byte-identical | 固定運算順序 + 單執行緒 BLAS |
| R3 | reward 權重 | `λ_mdd=1.0, λ_turnover=0.0015`（風控優先） |
| R4 | 滑價分離 | base_slippage_bps 屬市場模型，不入 reward 公式 |
| R5 | quality_flag | 股票缺值跳日、FRED missing_rate forward fill |
| R6 | hash 比對 | __init__ 一次性 fail-fast，step 不重算 |
| R7 | SMC 預計算 | __init__ 一次性 batch_compute，step 查表 |
| R8 | 容差分層 | 算術 1e-12 / 跨平台 1e-9 / 動作門檻 1e-6 |
