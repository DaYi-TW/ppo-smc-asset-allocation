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
