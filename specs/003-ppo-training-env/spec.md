# Feature Specification: PPO 訓練環境（PPO Training Environment）

**Feature Branch**: `003-ppo-training-env`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "建立 Gymnasium 相容的多資產投資組合訓練環境，作為 PPO 代理的互動介面。輸出將被未來的 PPO 訓練 feature 與回測 feature 消費。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 以隨機策略跑通環境（Priority: P1）

ML 研究者要在尚未訓練 PPO 之前，先驗證環境本身的正確性：給定 002 產出的 Parquet 快照與 001 計算的 SMC 特徵，環境應能完成完整 episode（從 2018-01-01 到 2026-04-29），每一步接受合法 action 並回傳 observation、reward、terminated、truncated、info，且不發生 NaN、shape 錯誤、超出範圍的部位。

**Why this priority**: 沒有可以跑通的環境，後續任何 PPO 訓練、reward 調參、ablation 都無法執行。這是整個 RL pipeline 的入口。

**Independent Test**: 不需要訓練模型；以 `np.random.dirichlet([1]*7)` 作為每步 action，跑滿一個 episode，驗證：(a) episode length 等於資料天數，(b) NAV 序列無 NaN，(c) reward 無 NaN/inf，(d) info dict 完整且 shape 正確。

**Acceptance Scenarios**:

1. **Given** 002 已產出全部 Parquet 快照、001 已計算全部 SMC 特徵、以 fixed seed=42 重設環境，**When** 以 Dirichlet 隨機策略連續呼叫 `step()` 直到 `terminated=True`，**Then** episode length == 資料總交易日數、最終 NAV 與 reward 累加值在不同機器上完全相同（byte-identical）。
2. **Given** 同上設定，**When** 比較兩次 reset(seed=42) 後的 episode trajectory，**Then** 完全一致（reproducibility 驗證）。

---

### User Story 2 - 驗證 reward 三項成分（Priority: P1）

ML 研究者需要證明 reward 函式確實包含「階段性報酬 − MDD 懲罰 − 交易成本懲罰」三項，並能個別關閉/開啟以做消融。在 `info` dict 中必須暴露三項分量原始值，便於下游分析。

**Why this priority**: 憲法 Principle III（Risk-First Reward）為 NON-NEGOTIABLE。若 reward 不含三項或無法個別檢視，整個論文核心主張不成立。

**Independent Test**: 設定 `lambda_mdd=0, lambda_cost=0` 跑一個 episode，所得 reward 序列應與「純 log return」完全相同（容差 1e-12）；再開啟兩項，跑同一 trajectory，info 中三項分量加總應等於最終 reward。

**Acceptance Scenarios**:

1. **Given** RewardConfig(lambda_mdd=0, lambda_cost=0)、固定隨機 action 序列，**When** 計算每步 reward，**Then** reward == log(NAV_t / NAV_{t-1})（容差 1e-12）。
2. **Given** RewardConfig(lambda_mdd=1.0, lambda_cost=0.0015)、同上 action 序列，**When** 檢查 info["reward_components"]，**Then** 包含 `log_return`、`drawdown_penalty`、`turnover_penalty` 三鍵，且 `log_return − drawdown_penalty − turnover_penalty == reward`。

---

### User Story 3 - SMC 特徵消融開關（Priority: P2）

研究者需要比較「有 SMC 特徵 vs. 純價格特徵」的 PPO 訓練效果。環境必須提供 config 開關，能在不修改其他程式碼的情況下，將 observation space 從 63 維（含 SMC）切換為 33 維（不含 SMC）。

**Why this priority**: 論文 Findings 章節需要 ablation 證明 SMC 特徵帶來增量價值；若環境無此開關，研究者必須維護兩個分支，違反可重現性。

**Independent Test**: 同一份 Parquet 資料、同一 seed，分別以 `include_smc=True` 與 `False` 重設環境，驗證 observation 維度分別為 63 與 33，且 33 維版本中前 24 維（價格）與後 9 維（macro+position）數值與 63 維版本對應位置完全相同。

**Acceptance Scenarios**:

1. **Given** PortfolioEnvConfig(include_smc=True)，**When** `env.observation_space.shape`，**Then** == (63,)。
2. **Given** PortfolioEnvConfig(include_smc=False)，**When** 同上，**Then** == (33,)。
3. **Given** 兩種 config 以 seed=42 reset 後的首日 obs，**When** 比對非 SMC 段，**Then** 完全相同（容差 0）。

---

### User Story 4 - Episode 完整 info 紀錄（Priority: P2）

研究者與後端工程師需要在訓練/推理時完整擷取每步狀態，作為戰情室前端可視化與事後 debug 之依據。`info` dict 必須包含當步權重、NAV、現金、各資產價值、turnover、reward 三項分量。

**Why this priority**: 微服務戰情室（feature 007）將消費這些 info 做即時圖表；若資訊不完整，前端必須繞回環境內部，違反 Principle IV（Service Decoupling）。

**Independent Test**: 跑一個 episode，將每步 info 收集為 list，驗證每筆都含預期 key set，且 NAV 序列首日 == 1.0、單調連續（無跳值）。

**Acceptance Scenarios**:

1. **Given** 任一 episode、任一步，**When** 檢查 `info` keys，**Then** 至少包含：`weights`(7,)、`nav`(scalar)、`cash`(scalar)、`asset_values`(6,)、`turnover`(scalar)、`reward_components`(dict)、`date`(ISO string)。
2. **Given** episode 首日，**When** `info["nav"]`，**Then** == 1.0。

---

### Edge Cases

- **資料 quality_flag != "ok"**：當當天某資產 `quality_flag == "missing_close"` 或 `"zero_volume"` 時，環境 MUST 跳過該日（將該日從 episode 序列中剔除），並於 `info["skipped_dates"]` 中累積；不得用 NaN 價格計算報酬。
- **NaN action**：若 agent 傳入含 NaN 的 action，環境 MUST 立即 raise `ValueError("Action contains NaN")`；不得靜默替換為均勻分配。
- **action 總和 ≠ 1**：若 action 元素和不為 1（容差 1e-6），環境 MUST 用 softmax 重正規化，並於 `info["action_renormalized"]` 標記 True；不得拒絕非法 action 中斷訓練。
- **單一資產持倉超過上限**：若任一資產權重 > 0.4，環境 MUST 將該超出部分等比例分配給其他資產（rebalance），並於 `info["position_capped"]` 標記。
- **第一日 reward**：episode 第 0 步無前日 NAV，reward MUST 強制為 0，並於 info 標示 `is_initial_step=True`。
- **資料邊界**：當 `current_index == len(data) - 1`，下一步 `step()` MUST 回傳 `terminated=True`，不再推進。
- **資產日曆不對齊**：若六檔資產某日存在但 FRED 利率該日為 NaN（FRED 部分節日不發布），環境 MUST 使用前一可用值（forward fill 僅針對無風險利率，不對價格做任何填補）。
- **滑價時序**：交易成本計算 MUST 使用「執行當下」價格（即 t 時刻的 close），不得用次日開盤；turnover 定義為 `0.5 * sum(|w_t − w_{t-1}|)`。
- **重設 seed**：`reset(seed=N)` MUST 同步重設 numpy、Gymnasium 內部、以及任何隨機資料切片邏輯的 seed；不得依賴全域 `np.random`。

## Requirements *(mandatory)*

### Functional Requirements

#### 環境介面

- **FR-001**: 環境 MUST 繼承 `gymnasium.Env`，實作 `reset(seed, options)`、`step(action)`、`close()`、`render()`（後者可為 no-op）。
- **FR-002**: 環境 MUST 宣告 `observation_space` 為 `Box(low=-inf, high=inf, shape=(D,), dtype=float32)`，其中 D 由 config 決定（含 SMC=63、不含 SMC=33）。
- **FR-003**: 環境 MUST 宣告 `action_space` 為 `Box(low=0.0, high=1.0, shape=(7,), dtype=float32)`，對應 [NVDA, AMD, TSM, MU, GLD, TLT, CASH] 七維權重。
- **FR-004**: 環境 MUST 接受 `gymnasium.utils.env_checker.check_env(env)` 全部檢查通過。

#### 資料載入

- **FR-005**: 環境啟動時 MUST 自 `data/raw/` 載入 002 產出的六檔股票 Parquet 與 FRED 利率 Parquet，並（若 `include_smc=True`）呼叫 001 函式庫計算 SMC 特徵；不得內含資料抓取邏輯。

#### Reward 函式

- **FR-006**: Reward 函式 MUST 形式為 `r_t = log(NAV_t / NAV_{t-1}) − λ_mdd × drawdown_t − λ_cost × turnover_t`，其中：
  - `drawdown_t = max(0, max(NAV_{0..t-1}) − NAV_t) / max(NAV_{0..t-1})`
  - `turnover_t = 0.5 * sum(|w_t − w_{t-1}|)`
- **FR-007**: 預設權重 MUST 為 `λ_mdd = 1.0`、`λ_cost = 0.0015`（風控優先型，sigma 級別與 log return 對齊）。
- **FR-008**: 滑價 MUST 以單邊 5 bps 計入 `turnover_penalty`：`turnover_penalty = (5e-4 + λ_cost_extra) × turnover_t`；config 可分別設定基礎滑價與額外懲罰。
- **FR-009**: `info["reward_components"]` MUST 包含 `log_return`、`drawdown_penalty`、`turnover_penalty` 三個 float key，且三者運算後等於 `reward`（容差 1e-9）。

#### Observation 結構

- **FR-010**: Observation 向量結構（`include_smc=True` 時 D=63）MUST 為：
  - `[0:24]` — 6 檔股票 × 4 個價格特徵（log_return_1d、log_return_5d、log_return_20d、volatility_20d）
  - `[24:54]` — 6 檔股票 × 5 個 SMC 特徵（BOS、CHoCh、FVG_distance、OB_touched、OB_distance）
  - `[54:56]` — 2 個 macro 特徵（無風險利率、無風險利率 20d 變化）
  - `[56:63]` — 7 維當前權重（含 cash）
- **FR-011**: 當 `include_smc=False` 時 D=33，跳過 `[24:54]` 區段，其他維度與位置保持不變。
- **FR-012**: Observation 數值 MUST 為 `float32`；任何 NaN 必須於環境內部偵測並轉為 0.0，同時於 `info["nan_replaced"]` 累計次數。

#### Action 處理

- **FR-013**: Action 維度 MUST 為 7（六檔股票 + cash）。
- **FR-014**: Action MUST 經過：(a) NaN 檢查→raise、(b) softmax 正規化（若元素和 ≠ 1 容差 1e-6）、(c) 0.4 上限封頂與重分配、(d) 寫入下一步 `weights`。
- **FR-015**: 環境 MUST 在 `info["action_raw"]`（原始）、`info["action_processed"]`（處理後）兩者同時暴露，便於 debug。

#### Episode 控制

- **FR-016**: Episode 結束條件 MUST 為「資料用盡」（即 `current_index == len(data) - 1`），回傳 `terminated=True`。
- **FR-017**: 環境 MUST 不支援 `truncated`（永遠回傳 `False`），除非未來明確新增 episode 長度限制需求。
- **FR-018**: `reset()` 預設 MUST 從資料起始日（2018-01-01 之首交易日）開始；config 可設定不同起始日（用於滾動視窗訓練）。

#### 可重現性

- **FR-019**: `reset(seed=N)` MUST 將 numpy、Python `random`、環境內部任何隨機元件以同一 seed 重設；不依賴全域 `np.random.seed`。
- **FR-020**: 在相同 commit、相同 Parquet 雜湊、相同 seed、相同 action 序列下，跨平台（Linux/macOS/Windows）episode trajectory 數值差異 MUST ≤ 1e-9。
- **FR-021**: 環境 MUST 於 `info["data_hashes"]` 暴露每檔資產 Parquet 的 SHA-256，與 002 metadata 比對；若不符 raise `RuntimeError("Snapshot hash mismatch")`。

#### Config 與 ablation

- **FR-022**: 環境 MUST 接受 `PortfolioEnvConfig` dataclass，欄位至少包含：`include_smc: bool`、`reward_config: RewardConfig`、`position_cap: float`、`base_slippage_bps: float`、`initial_nav: float`、`start_date: date | None`、`end_date: date | None`、`assets: list[str]`。
- **FR-023**: `RewardConfig` MUST 為獨立 dataclass，欄位至少包含：`lambda_mdd: float`、`lambda_cost_extra: float`（基礎 5 bps 之外的額外懲罰，預設 0.001 → 總 turnover_penalty = 0.0015 × turnover）。
- **FR-024**: 任何 config 欄位修改 MUST 不需要重新匯入或重啟程序，僅需建立新環境實例。

#### 跨層介面

- **FR-025**: 環境 MUST 為純 Python 函式庫；不得內含 HTTP server、Kafka producer、資料庫連線（這些屬於 005-008 features）。
- **FR-026**: `info` dict 中所有 numpy 陣列 MUST 可序列化為 JSON（先轉 list/scalar）；提供輔助函式 `info_to_json_safe(info) -> dict`。

#### 視覺化（最小可行）

- **FR-027**: 環境 MUST 提供 `render(mode="human")` 之外的 `render(mode="ansi") -> str` 模式，回傳當步狀態之文字摘要（日期、NAV、權重、reward 三項）；圖形化視覺化留給 feature 007（戰情室前端）。

### Key Entities *(include if feature involves data)*

- **PortfolioEnv**: Gymnasium 環境主類別，封裝資料載入、step 邏輯、reward 計算、reset 控制。狀態包含 `current_index`、`current_weights`、`nav_history`、`peak_nav`、`prng`。
- **PortfolioEnvConfig**: 環境靜態設定。屬性：`include_smc`、`reward_config`、`position_cap`、`base_slippage_bps`、`initial_nav`、`start_date`、`end_date`、`assets`、`data_root`。
- **RewardConfig**: Reward 函式參數。屬性：`lambda_mdd`、`lambda_cost_extra`。預設 `lambda_mdd=1.0, lambda_cost_extra=0.001`（總 turnover_penalty 係數 = 0.0015，含 5 bps 基礎滑價）。
- **Observation Vector**: shape=(63,) 或 (33,) 的 float32 陣列；分區結構固定，由 FR-010/FR-011 規範。
- **Action Vector**: shape=(7,) 的 float32 陣列；對應 [NVDA, AMD, TSM, MU, GLD, TLT, CASH] 權重。
- **Episode Log**: 每步 `info` dict 之累積；下游 005 推理服務、007 戰情室將消費此資料結構。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 以隨機 Dirichlet 策略跑滿一個 episode（2018-01-01 至 2026-04-29，約 2090 個交易日），單機 CPU 環境總耗時 < 30 秒。
- **SC-002**: 跨平台（Linux/macOS/Windows）以相同 seed 與 action 序列跑同 episode，最終 NAV 數值差異 ≤ 1e-9。
- **SC-003**: `gymnasium.utils.env_checker.check_env(env)` 在 `include_smc=True` 與 `False` 兩種設定下皆 100% 通過，無 warning。
- **SC-004**: Reward 三項分量（log_return、drawdown_penalty、turnover_penalty）加總 == reward，全 episode 容差 ≤ 1e-9。
- **SC-005**: 連續呼叫 `reset(seed=42)` 兩次後 step 1000 次，trajectory（NAV 序列、reward 序列、weights 序列）byte-identical（MD5 相同）。
- **SC-006**: 單元測試覆蓋率 ≥ 90%（憲法 Spec SC-004 對齊）。
- **SC-007**: 將 `lambda_mdd=0, lambda_cost_extra=−0.0005`（僅留 5 bps 基礎滑價中的 0）使環境退化為純 log return reward，所得 reward 序列與手算結果差異 ≤ 1e-12（消融驗證）。
- **SC-008**: `info` dict 經 `info_to_json_safe()` 後可直接 `json.dumps()` 不報錯，且來回轉換無精度損失（float64 內）。

## Assumptions

- 002 已產出全部六檔股票（NVDA、AMD、TSM、MU、GLD、TLT）與 FRED DTB3 利率 Parquet 快照於 `data/raw/`，且 metadata.json 之 SHA-256 已 commit。
- 001 SMC 特徵引擎已實作完成，可作為 Python 函式庫被 import；其輸出 schema 穩定（BOS/CHoCh/FVG/OB 五個 SMC 特徵欄位）。
- 訓練與推理皆於單機 CPU 環境執行；GPU 加速為 PPO 訓練 feature 之考量，不在本 feature 範圍。
- 交易日曆採六檔股票之交集（NYSE 日曆 + GLD/TLT 交易日）；FRED 無風險利率以 forward fill 對齊。
- 滑價模型採固定 5 bps（單邊），不模擬市場衝擊、無 bid-ask spread 模型；更精細的市場微觀結構留給未來 feature。
- 起始 NAV 預設為 1.0（無單位淨值），便於跨平台與跨資產比較。
- 環境內部不執行 PPO 訓練、不呼叫 stable-baselines3；僅提供 Gymnasium 相容介面，由後續 feature（004 PPO 訓練 loop）消費。
