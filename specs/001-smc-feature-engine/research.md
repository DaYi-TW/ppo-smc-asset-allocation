# Phase 0 Research: 001-smc-feature-engine

**Date**: 2026-04-29
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

本文件解決 plan.md Technical Context 中所有 NEEDS CLARIFICATION，並為 Phase 1
（data-model、contracts、quickstart）提供決策基礎。每項決策包含：**Decision** /
**Rationale** / **Alternatives considered** 三段。

---

## R1. BOS / CHoCh 判定演算法

**Unknown**: SMC 的 BOS（Break of Structure）與 CHoCh（Change of Character）有多種社群
流派的定義（ICT / Mentfx / 純結構派），需選定一個並能寫入 docstring 作為可重現規則。

### Decision

採用 **基於 swing point 的 fractal 結構判定法**，具體規則如下：

1. **Swing High / Swing Low 偵測**：給定參數 `swing_length L`（預設 5），第 `i` 根 K 棒
   為 swing high 若 `high[i] > high[j]` 對所有 `j ∈ [i-L, i+L] \ {i}`；swing low 對稱
   定義（嚴格大於 / 嚴格小於，平手不採計）。需有 `L` 根之後的 K 棒才能確認 swing point，
   故 swing point 為 **delayed signal**（落後 L 根）。
2. **趨勢狀態**：以最新一個確認的 swing high `H_last` 與 swing low `L_last` 維護趨勢狀態：
   - **Bullish**：最新 swing high 高於前一個 swing high 且最新 swing low 高於前一個 swing low
   - **Bearish**：對稱
   - **Neutral**：初始狀態或結構未明確
3. **BOS（Break of Structure，趨勢延續）**：在 Bullish 狀態下，K 棒收盤價 `close[i]`
   突破 `H_last`（即 `close[i] > H_last`），則 `bos_signal[i] = +1`；在 Bearish 狀態下
   `close[i] < L_last` 則 `bos_signal[i] = -1`。否則 `0`。
4. **CHoCh（Change of Character，趨勢反轉）**：在 Bullish 狀態下，`close[i] < L_last`
   則 `choch_signal[i] = -1` 且趨勢狀態翻轉為 Bearish；對稱定義 `+1`。
5. **衝突優先序**（spec FR-019）：CHoCh 優先於 BOS — 同根 K 棒同時符合條件時，
   `choch_signal` 設值、`bos_signal` 設 0。

**判定基於收盤價而非最高/最低價** — 避免影線假突破誤判。

### Rationale

- **可重現**：演算法純函數式，無啟發式調參，給定相同 OHLCV 與 `swing_length` 必產出
  相同結果。符合憲法 Principle I。
- **可解釋**：規則可一句話描述（「收盤突破前波段高低點」），符合憲法 Principle II。
- **文獻基礎**：fractal swing 偵測為 Bill Williams（1995）提出的標準技術分析手法，
  ICT/SMC 社群普遍採用此基礎判定 swing 結構（雖各流派對 swing length 的預設值不同，
  L=5 為常見預設）。
- **與本研究範圍契合**：論文關注 PPO 觀測空間的特徵化，不需在演算法層面追求 SMC 流派
  最前沿；選擇「最常見 + 可重現」的版本即可。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| ICT 純結構派（基於 displacement candles） | displacement 的「強烈動能」需主觀門檻，違反可重現性 |
| 多時間框架（HTF）結構判定 | 本 feature 僅日線單時框，跨時框屬未來 feature |
| ZigZag 演算法 | 結果隨 deviation 參數高度敏感，且偵測點不穩定（會 repaint） |
| 僅基於最高/最低價突破 | 影線易產生假訊號，不符合 SMC 實務「收盤確認」原則 |

---

## R2. FVG（Fair Value Gap）邊界與大小門檻

**Unknown**: FVG 為三根 K 棒間的價格不連續區，但各流派對「邊界」（用最高/最低價還是
實體）與「最小幅度」（過濾雜訊）有差異。

### Decision

採用 **三 K 棒高低價缺口法 + 可選最小幅度過濾**：

1. 給定連續三根 K 棒 `bar[i-2]`、`bar[i-1]`、`bar[i]`：
   - **Bullish FVG**：若 `low[i] > high[i-2]`，則在 `[high[i-2], low[i]]` 區間為 FVG。
     形成位置記錄為 `i-1`（中間 K 棒），上下緣分別為 `low[i]`（top）與 `high[i-2]`（bottom）。
   - **Bearish FVG**：若 `high[i] < low[i-2]`，則在 `[high[i], low[i-2]]` 區間為 FVG。
2. **最小幅度門檻**：FVG 高度 `(top - bottom) / close[i-1]` 須 ≥ `fvg_min_pct`（預設 0.001
   = 0.1%），否則視為雜訊忽略。此參數由呼叫方顯式傳入（spec FR-017）。
3. **填補判定**：FVG 形成後，後續任一 K 棒 `j > i`：
   - Bullish FVG **完全填補**：若 `low[j] ≤ bottom`
   - Bearish FVG **完全填補**：若 `high[j] ≥ top`
4. **`fvg_distance_pct[i]` 計算**：取所有未填補 FVG 中 **最近一個**（以時間距離為準），
   計算 `(close[i] - fvg_midpoint) / close[i]` 為帶符號百分比。若無未填補 FVG，輸出
   `NaN`（spec FR-003）。

### Rationale

- **三 K 棒高低價缺口法**為 SMC 社群最廣泛採用的精確定義（ICT 創始定義即為此版本），
  與其他變種相比語意明確、無模糊空間。
- **最小幅度門檻**使用「相對中間 K 棒收盤的百分比」而非絕對價格，使參數對不同價位
  資產具可移植性（NVDA $500 與 GLD $200 用同一參數有意義）。
- **以 midpoint 計算距離**（而非 top/bottom）：FVG 在 SMC 理論中為「price magnet」，
  midpoint 為其「磁吸中心」，較 top/bottom 更穩定地反映回測距離。
- **NaN 哨兵值**：與 spec Assumptions 第二條一致，PPO 環境可自行處理（mask 或
  forward fill）。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 以實體（open/close）而非最高/最低判定缺口 | 過於嚴格，偵測到的 FVG 數量過少；社群慣例為高低價版本 |
| 部分填補（mitigation）也視為已填補 | 部分填補後 FVG 仍可作為支撐/壓力，過早移除會錯失訊號 |
| 距離以 top/bottom 較近邊界計算 | 距離訊號隨價格位置在區間上下會跳變，干擾 RL 學習 |
| 不設最小幅度門檻 | 高頻雜訊缺口（< 0.05%）數量過多，觀測空間訊噪比下降 |

---

## R3. Order Block 有效期與距離標準化

**Unknown**: OB 的「有效期」（多少根 K 棒後失效）與距離標準化的分母選擇（ATR window
長度）。

### Decision

1. **OB 識別規則**：在 swing high / swing low 之前，**最後一根反向 K 棒** 視為 OB。
   - **Bullish OB**（多方訂單塊）：在 swing low 形成前，最後一根紅 K 棒（close < open），
     範圍為 `[low, high]` of 該 K 棒。
   - **Bearish OB**：對稱（swing high 前最後一根綠 K 棒）。
2. **OB 有效期**：`ob_lookback_bars` 參數預設 50（即從形成後 50 根 K 棒內有效），
   參數由呼叫方傳入（spec FR-017）。
3. **OB 失效條件**（兩擇一）：
   - **時間失效**：超過 `ob_lookback_bars` 根 K 棒後自動失效。
   - **結構失效**：價格收盤穿越 OB 反向邊界（Bullish OB 收盤 < OB low；Bearish OB 收盤
     > OB high）— 表示 OB 防守失敗。
4. **`ob_touched[i]`**：當前 K 棒的價格範圍 `[low[i], high[i]]` 與最近一個 **有效**
   OB 的範圍有交集，則 `True`，否則 `False`。
5. **`ob_distance_ratio[i]`**：`(close[i] - ob_midpoint) / atr[i]`，其中 `atr[i]` 為
   `ATR(14)`（Wilder's ATR with smoothing window = 14）。若無有效 OB 或 ATR 未就緒
   （前 14 根），輸出 `NaN`。

### Rationale

- **「最後一根反向 K 棒」定義**為 ICT 社群最核心的 OB 定義，相對於 imbalance-based
  或 order flow-based 變種，此定義僅依賴 OHLCV 不需 tick data。
- **ATR(14) 為標準化分母**：金融時序波動度標準化的工業標準，使距離特徵在不同波動度
  期間（如 2020 COVID vs. 2025 平靜期）保持可比性。
- **雙重失效條件**：時間失效避免「永久 OB」累積過多；結構失效對應 SMC 實務「OB 被破
  即失效」原則。
- **預設 50 根**：日線 50 根約兩個半月，足夠涵蓋波段交易週期；參數可由使用者覆蓋。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 用收盤價標準化（`close[i]`）而非 ATR | 不反映波動度差異，靜態股票期間訊號弱 |
| 使用實體（open/close）區間定義 OB | 排除影線資訊，OB 邊界實務上常於影線觸碰時反應 |
| 永不失效（lifetime OB） | 累積數量無上限，計算成本與訊噪比惡化 |
| ATR window 20 或 50 | 14 為 Wilder 原始建議與社群標準；20/50 雖更平滑但反應遲鈍 |

---

## R4. 視覺化函式庫選擇：mplfinance vs. plotly

**Unknown**: spec FR-010 要求支援 PNG 與 HTML 兩種輸出格式（呼叫方擇一），需選定底層
函式庫。

### Decision

**雙函式庫策略**：

- **PNG 輸出**：使用 **mplfinance**（基於 matplotlib），提供 `visualize(..., format="png")`。
- **HTML 輸出**：使用 **plotly**，提供 `visualize(..., format="html")`。

兩者共享同一前端公開函式 `visualize()`，內部依 `format` 參數分派。

### Rationale

- **mplfinance**：為 K 線圖事實標準函式庫，與 matplotlib 生態整合，PNG 輸出檔案小
  （典型 < 100 KB）、跨平台 deterministic（給定資料 + 樣式產出 byte-near-identical
  PNG，僅 metadata 區塊有差）、論文與 Jupyter Notebook 友善。
- **plotly**：HTML 輸出原生互動（縮放、hover、切換 series），對非技術背景審查者
  最友善（spec SC-005「5 分鐘理解 BOS 標記」），自含 standalone HTML 不需 server。
- **兩者共存可行**：plotly 與 matplotlib 可同處一個 Python 環境，無 ABI 衝突；對應
  spec FR-010「擇一」由呼叫方決定，不需強制使用者只裝其中一個。
- **依賴成本**：兩者皆為純 Python wheel，加總安裝體積約 60 MB，可接受。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 僅用 mplfinance（PNG 與 HTML 皆出 PNG-in-HTML） | HTML 失去互動性，違反 spec SC-005 的「5 分鐘理解」目標 |
| 僅用 plotly（PNG 透過 kaleido） | kaleido 在 Windows 偶有 deterministic 問題；多一層 dependency |
| Bokeh | K 線圖支援需額外 plugin，社群活躍度低於 mplfinance/plotly |
| TradingView Lightweight Charts（JS） | 純前端，需打包 JS bundle，逾本 feature 純 Python 範圍 |
| 自寫 SVG | 維護成本高，且重新發明輪子 |

### 跨平台 PNG byte-identical 風險

- mplfinance/matplotlib 的 PNG 輸出在不同 freetype 版本下字型 anti-aliasing 可能差異
  幾個 byte。**緩解措施**：
  - 視覺化函式輸出 **不參與 SHA-256 一致性比對**（spec SC-002 的 byte-identical 要求
    僅針對特徵 DataFrame，不含視覺化輸出）。
  - 視覺化測試以「圖中是否含特定 marker」（structural test）取代 byte-level 比對。
- 此風險於 plan.md Constitution Check Principle I 段落明確記錄，不視為違規。

---

## R5. Parquet 跨平台 byte-identical 浮點輸出

**Unknown**: spec SC-002 要求「跨平台執行的輸出 DataFrame 在所有非 NaN 浮點欄位上的最大
絕對誤差 ≤ 1e-9」。此要求關乎 (a) 計算過程是否產生跨平台浮點差異、(b) Parquet 序列化
是否保持 bit-exact。

### Decision

1. **計算層**：所有特徵計算 MUST 使用 numpy / pandas 的 `float64`（IEEE 754 雙精度）；
   禁止使用 `float32` 或加速套件（如 `bottleneck`、`numexpr`）的非 IEEE-strict 模式。
2. **避免 reduce 順序敏感操作**：例如 `np.sum` 於不同 CPU 架構下若啟用 SIMD，floating
   reduce 順序可能不同。緩解：對需要 reduce 的步驟（如 ATR 平均），使用顯式 Python loop
   或 `np.cumsum` 等順序固定的運算，必要時於 docstring 標註「avoid SIMD reduce」。
3. **Parquet 序列化**：本 feature **不直接寫 Parquet**。下游若需快照，由呼叫方使用
   pyarrow 寫入；pyarrow 的 `float64` 序列化為 IEEE 754 bit-exact，跨平台讀寫保證
   往返一致（已驗證為 pyarrow 文件保證）。
4. **驗收測試**：CI 在 ubuntu-latest / macos-latest / windows-latest 三平台執行同一
   單元測試，比對輸出 DataFrame 的所有 `float64` 欄位 `np.allclose(rtol=0, atol=1e-9)`。

### Rationale

- IEEE 754 雙精度的算術運算（+, -, *, /, sqrt）在所有現代 x86_64 CPU 上 bit-exact，
  跨平台一致性風險主要來自 reduce 順序與 SIMD vectorization。
- 「1e-9」門檻寬鬆於 bit-exact（後者 = 0），允許極少數無法避免的浮點差異（如 `np.std`
  內部的 reduce），仍能滿足金融訊號用途。
- 不涉及 PyTorch / GPU 計算，避免 CUDA 非確定性的更大風險（憲法 Principle I 要求的
  fixed seed 在本 feature 因無亂數而 N/A）。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 使用 `numpy.float128` | 不跨平台（Windows 僅支援 float64）、效能差 |
| 改用 Decimal 任意精度算術 | 效能不可接受（spec SC-001 30 秒批次目標難達） |
| 放寬至 1e-6 一致性 | 訊號尺度小（如 BOS 邊界判定）下，1e-6 可能跨越判定邊界導致 categorical 不一致 |
| 嚴格 bit-exact（atol=0） | numpy reduce 在不同 BLAS 版本下無法保證；目標過嚴 |

---

## R6. 增量計算的內部狀態結構

**Unknown**: spec FR-008 要求增量模式對單根新 K 棒輸出，且輸出與批次模式對應位置完全
相等。需設計可序列化的「狀態」物件，承載批次計算累積的中介資訊（已偵測的 swing
points、未填補 FVG 列表、有效 OB 列表）。

### Decision

定義 **`SMCEngineState`** dataclass（不可變、`frozen=True`），包含：

```python
@dataclass(frozen=True)
class SMCEngineState:
    last_swing_high: Optional[SwingPoint]      # 最近確認 swing high
    last_swing_low: Optional[SwingPoint]       # 最近確認 swing low
    prev_swing_high: Optional[SwingPoint]      # 用於趨勢判定
    prev_swing_low: Optional[SwingPoint]
    trend_state: Literal["bullish", "bearish", "neutral"]
    open_fvgs: tuple[FVG, ...]                 # 未填補 FVG 列表（含形成時間）
    active_obs: tuple[OrderBlock, ...]         # 有效 OB 列表
    atr_buffer: tuple[float, ...]              # ATR 計算用的最近 14 個 TR 值
    bar_count: int                             # 已處理 K 棒數，用於 OB 時間失效
    params: SMCFeatureParams                   # 不可變參數快照
```

`incremental_compute(prior_df, new_bar, state) -> (new_row, updated_state)` 接收前次
回傳的 `state`，產出新一列特徵與新 `state`。

### Rationale

- **Frozen dataclass**：保證狀態不可變，避免「同一 state 被多次呼叫產生不同結果」的
  陷阱；每次更新返回新 instance。
- **Tuple 而非 List**：保持 hashable + immutable，符合 frozen dataclass 慣例。
- **明確包含 `params`**：保證 batch 與 incremental 用同一參數，避免漂移。
- **可序列化**：所有欄位為 primitive 或 dataclass，可直接 `pickle.dumps()` 用於跨進程
  傳遞或快照保存（雖非當前 feature 範圍，但為未來服務化預留）。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 將 state 隱藏於 module-level global | 違反純函數原則，無法平行處理多商品 |
| 用 Class instance with mutable state | 容易產生 race condition 或重複呼叫不一致 |
| 將整段 prior_df 重新計算（不維護 state） | 違反 spec SC-003「< 10 ms」延遲目標 |
| 使用 dict 而非 dataclass | 無 type safety，IDE 補全不友善 |

---

## R7. 套件版本鎖定策略（憲法 Principle I）

**Unknown**: 憲法 Principle I 要求「套件版本鎖定」與「實驗結果同 commit 提交」。本 feature
為函式庫，需明確版本鎖定機制。

### Decision

1. **`pyproject.toml`** 宣告**最低版本**（鬆鎖）：例如 `pandas>=2.0,<3.0`、
   `numpy>=1.24,<2.0`、`pyarrow>=14.0`、`mplfinance>=0.12.10`、`plotly>=5.18`。
   允許 patch 升級以獲取 bug fix。
2. **`requirements-lock.txt`**（於 repo 根）：以 `pip-compile` 或 `pip freeze`
   產生 **完整版本鎖定清單**（含 transitive deps），CI 與 quickstart 安裝時用此檔案
   保證 byte-exact 環境。
3. **CI 驗證**：CI matrix 同時跑「lock 檔安裝」與「最低版本安裝」兩種模式，後者捕捉
   套件升級造成的 silent breakage。
4. **論文與實驗綁定**：論文發表的實驗 commit 同步紀錄 `requirements-lock.txt`、Python
   版本（`.python-version`）、OS 版本（CI artifact）。

### Rationale

- **鬆鎖 + lock 檔雙層**為 Python 社群成熟模式（如 Poetry、pip-tools），相容於 pip /
  uv / pdm 等工具鏈。
- **CI matrix** 兼顧「保守可重現」（lock 檔）與「前瞻發現破裂」（最低版本）。

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| 僅 lock 檔，不寫 pyproject 範圍 | 升級 deps 時無上限參考，diff 全 lock 檔難 review |
| Pin 死特定版本（`==`）於 pyproject | 與其他 feature 整合時 conflict 機率高 |
| 不 lock，靠 README 寫版本 | 實際安裝 transitive deps 隨時間漂移，無法重現 |
| 使用 conda 環境檔 | 與 PyPI 主流分歧，論文重現門檻高 |

---

## 整合摘要：Phase 1 設計依據

以上七項決策共同定義了 Phase 1 將生成之文件的具體結構：

- **data-model.md**（Phase 1 輸出）將依 R1-R3 定義 `SwingPoint`、`FVG`、`OrderBlock`、
  `SMCFeatureParams`、`SMCEngineState`、`FeatureRow` 等實體；依 R5 鎖定所有數值欄位
  為 `float64`、categorical 為 `int8` 或 `bool`。
- **contracts/**（Phase 1 輸出）將定義公開 API 函式簽章 `batch_compute`、
  `incremental_compute`、`visualize`，採 Python type stubs（`.pyi`）格式。
- **quickstart.md**（Phase 1 輸出）將示範從 `data/raw/nvda_*.parquet`（feature 002 輸出）
  讀取 → `batch_compute` → `visualize` → `pytest` 完整流程，使用 R7 lock 檔安裝環境。

無剩餘 NEEDS CLARIFICATION。Phase 0 完成。
