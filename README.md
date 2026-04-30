# 基於PPO與SMC之動態多資產配置與微服務戰情室系統

## 資源與參考連結
- **[簡報/規格書 Proposed Design]**: [Google Slides Presentation](https://docs.google.com/presentation/d/1TU4X4ZUnunU1NLg83RluyfNbQz_qsY_O/edit?usp=sharing&ouid=106316695064653404133&rtpof=true&sd=true)
- **[展示影片 Video Demo]**: [YouTube Video (10 minutes)](https://www.youtube.com/watch?v=0eg7N7yPJR4)
- **[對話紀錄 / Gemini]**: [Gemini Shared Chat](https://gemini.google.com/share/1fdbf1c487f5)
- **[對話紀錄 / NotebookLM]**: [NotebookLM Notebook](https://notebooklm.google.com/notebook/b34bfe6e-117d-4b8a-ba78-cad985adcc8c)
- **[對話紀錄 / ChatGPT (投影片製作)]**: [ChatGPT Shared Chat](https://chatgpt.com/share/69ef1369-434c-83a7-b162-5cd69af07ce7)
- **[對話紀錄 (Related Work 參考資料)]**: [Perplexity Search](https://www.perplexity.ai/search/2bf7eda8-7666-45d9-8312-b1abf824477f#14)

---

## 1. Introduction (A. to F. 摘要)
*(詳見：[完整版 Introduction](docs/introduction_revised.md))*

本研究提出一套整合**近端策略最佳化 (PPO)** 與**聰明錢概念 (SMC)** 的多資產動態配置框架，並透過微服務架構開發戰情室系統以確保決策透明度：
- **動機及引題 (Attention Getter & Motivation)**：量化市場與 AI 基礎設施高速發展，單純追逐高成長資產的風險同步升高。
- **挑戰 (But)**：傳統資產配置（如 Markowitz 模型）無法快速適應政經環境的結構性轉變 (Regime shift)，且大眾技術指標具有滯後性。
- **解藥 (Cure)**：將 SMC 的市場微觀結構概念精準量化，結合 PPO 動態配置優點以克服上述痛點。
- **方法設計 (Development)**：區分攻擊型、避險型與現金部位，採用 React + Spring Boot 微服務架構實作視覺化系統。
- **實驗 (Experiments)**：收集多年度歷史數據，評估年化報酬、最大回撤 (MDD) 與夏普比率等關鍵績效。
- **發現 (Findings)**：預期能有效實現風險移轉，兼具市場動態適應能力與金融科技工程落地可行性。

---

## 2. Related Work (文獻探討摘要)
*(詳見：[完整版 Related Work](docs/related_work.md))*

本研究的文獻基礎建構於四大面向，以突顯 PPO 與 SMC 結合之前瞻價值：
1. **傳統資產配置與其侷限性**：儘管奠定基礎，但在極端事件下其高回撤風險已不足以應對現代市場。
2. **深度強化學習於資產配置之發展**：PPO 已獲實證在投資組合中表現亮眼且報酬豐厚，但特徵設計較少著墨機構流動性。
3. **聰明錢概念 (SMC) 與市場結構量化之探討**：為解決傳統指標滯後所造成的風險，我們將實務上的 FVG、OB 等特徵補足並首度整合入 RL 觀測狀態中。
4. **AI 交易系統架構與微服務戰情室**：參考業界實務建構視覺化系統，有效消弭「AI 黑箱」的隱患。

---

## 3. Proposed Design (規格書摘要)
*(詳見：[完整版 Proposed Design](docs/proposed_design.md))*

本系統的具體設計已獨立整理為規格書，涵蓋四大模組以支撐 PPO 與 SMC 融合之設計藍圖：
1. **多資產投資組合板塊設計 (Risk Buckets)**：系統將資金池分化為攻擊型 (AI 與半導體股)、避險型 (黃金與美債) 以及絕對安全現金等三階板塊，達成風險與報酬的自適應移轉。
2. **強化學習模型規格 (PPO Model)**：將模型神經網狀態擴展涵蓋 SMC 等流動性指標，由代理人輸出精細資金比重，並在獎勵函數中懲罰高回撤與過度換手造成的滑價成本。
3. **SMC 特徵量化工程 (Quantification)**：正式將市場行為轉化為物理數值，計算出 FVG 距離百分比、OB 的碰觸次數/距離，與 BOS/CHoCh 引發的性格連續改變特徵，避開傳統技術分析盲點。
4. **微服務架構與戰情室系統 (Microservices & War Room)**：後台使用 Spring Boot API 網關與 Kafka 負責訂單與分析解耦；前端結合 React 持續展現實時資產圖譜、SMC K線特徵與投組淨值，體現高度監控信任。

---

## 4. 資料快照 (Data Ingestion)

本專案的所有 PPO 訓練、回測、SMC 特徵計算皆從 commit 進 repo 的 Parquet 快照載入，以保證憲法 Principle I（可重現性）— 任何研究者在同一 commit 下執行必須得到位元組相同的數值。

- **規格與快速上手**：[`specs/002-data-ingestion/quickstart.md`](specs/002-data-ingestion/quickstart.md)
- **公開 API 契約**：[`specs/002-data-ingestion/contracts/api.pyi`](specs/002-data-ingestion/contracts/api.pyi)
- **CLI 契約**：[`specs/002-data-ingestion/contracts/cli.md`](specs/002-data-ingestion/contracts/cli.md)
- **資料快照位置**：`data/raw/`（7 個 `*.parquet` + 對應 `*.parquet.meta.json`，總和 < 10 MB）

跨平台位元組一致性透過 Docker dev container 鎖定（pandas / pyarrow patch 版本由 `requirements-lock.txt` 釘住）。常用指令：

```bash
docker compose run --rm dev ppo-smc-data fetch       # 第一次抓全部 7 個快照
docker compose run --rm dev ppo-smc-data verify      # 比對 SHA-256 / row_count / schema
docker compose run --rm dev ppo-smc-data rebuild --start 2018-01-01 --end 2026-04-29
```

`fetch` 需要 `FRED_API_KEY` 環境變數（[免費註冊](https://fred.stlouisfed.org/docs/api/api_key.html)），`verify` 純本地不需網路，CI 必跑。

---

## 5. SMC 特徵引擎（feature 001）

純函式庫，將 OHLCV 轉為五欄 SMC 特徵（`bos_signal`、`choch_signal`、`fvg_distance_pct`、`ob_touched`、`ob_distance_ratio`），憲法 Principle II（可解釋性）：每個特徵皆有明文判定規則 + 視覺化函式。

- **規格與快速上手**：[`specs/001-smc-feature-engine/quickstart.md`](specs/001-smc-feature-engine/quickstart.md)
- **公開 API 契約**：[`specs/001-smc-feature-engine/contracts/api.pyi`](specs/001-smc-feature-engine/contracts/api.pyi)

```python
from data_ingestion.loader import load_asset_snapshot
from smc_features import batch_compute, SMCFeatureParams

df = load_asset_snapshot("NVDA")
result = batch_compute(df, params=SMCFeatureParams())
print(result.output[["bos_signal", "fvg_distance_pct", "ob_touched"]].tail())
```

跨平台位元組一致性已於 CI 三平台矩陣（Linux / macOS / Windows）驗證 ≤ 1e-9（憲法 SC-002）。

---

## 6. PPO 訓練環境（feature 003）

Gymnasium 0.29+ 多資產組合配置環境，串接 002 快照 + 001 SMC 特徵作為 observation，輸出 7 維 simplex（6 檔股票 + CASH）；reward 結合 log return、最大回撤懲罰、turnover 懲罰（憲法 Principle III 風險優先）。

- **規格與快速上手**：[`specs/003-ppo-training-env/quickstart.md`](specs/003-ppo-training-env/quickstart.md)
- **公開 API 契約**：[`specs/003-ppo-training-env/contracts/api.pyi`](specs/003-ppo-training-env/contracts/api.pyi)
- **info schema**：[`specs/003-ppo-training-env/contracts/info-schema.json`](specs/003-ppo-training-env/contracts/info-schema.json)

```python
from portfolio_env import make_default_env
import numpy as np

env = make_default_env("data/raw/", include_smc=True)
obs, info = env.reset(seed=42)
rng = np.random.default_rng(42)
while True:
    action = rng.dirichlet(np.ones(7)).astype(np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated:
        break
print(f"final NAV={info['nav']:.4f}")
```

Observation shape `(63,)`（含 SMC）或 `(33,)`（純價格 + macro + 權重 ablation 模式）；env 對 ``__init__`` 階段一次性對 6 檔股票 + DTB3 重算 SHA-256，與 002 metadata 不符立即 raise（fail-fast、Principle I）。
