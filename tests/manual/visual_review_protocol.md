# SMC 視覺覆核受試者協議（Visual Review Protocol）

對應 spec **SC-005**：請至少 3 位非本專案開發者，於 5 分鐘內以視覺辨識
SMC 特徵在 K 線圖上的呈現。目標：在事先給定一頁 SMC 速查卡的條件下，
80% 受試者能正確識別 swing high / swing low、FVG 帶、OB 帶、BOS / CHoCh 標籤。

本文件對應任務 **T039**，作為 Phase 4 完工的一部分；驗收依據獨立於自動化
測試（後者僅驗 `visualize()` 產出檔案能被讀取與含關鍵元素，不驗肉眼可讀性）。

## 1. 受試者條件

* 至少 1 名 ML / 量化研究背景但**未接觸過 SMC** 的人。
* 至少 1 名軟體工程背景。
* 不限定金融背景，避免「先驗識別」污染辨識率。

## 2. 預備材料（受試者收到）

1. 一頁 SMC 速查卡（PDF），內容：
   * Swing High / Swing Low 視覺記號（紅色倒三角 / 綠色三角）。
   * FVG 帶配色（藍色半透明矩形）。
   * OB 帶配色（橘色半透明矩形）。
   * BOS / CHoCh 文字標註（紫色 = CHoCh、藍色 = BOS）。
2. 一張由本套件產出的測試 PNG（建議：NVDA 2024 H1，6 個月窗），呼叫範例：

   ```python
   from smc_features import batch_compute, SMCFeatureParams, visualize
   import pandas as pd
   df = pd.read_parquet("data/raw/nvda_daily_20180101_20260429.parquet")
   br = batch_compute(df, SMCFeatureParams(), include_aux=True)
   visualize(
       br.output,
       (pd.Timestamp("2024-01-02"), pd.Timestamp("2024-06-28")),
       "review_nvda_2024H1.png",
       fmt="png",
       params=SMCFeatureParams(),
   )
   ```

3. 一份書面題目（5 題，每題單選 / 短答）：
   * Q1：圖中**最後一個** swing high 的價位約為？
   * Q2：圖中是否存在尚未填補的 FVG？若有，方向為何？
   * Q3：圖中是否出現 CHoCh 訊號？方向？
   * Q4：圖底參數 footnote 是否清晰可讀？（是 / 否）
   * Q5：本圖最讓你困惑的視覺元素是？（開放）

## 3. 流程

| 階段 | 時間上限 | 內容 |
|------|----------|------|
| 速查卡熟悉 | 2 分鐘 | 受試者自行閱讀，不問問題 |
| 圖片觀察 | 2 分鐘 | 純看圖，不能問 |
| 答題 | 1 分鐘 | 寫下答案，不可回頭看圖 |

主持人不得提示「正確」答案，僅紀錄受試者選擇。

## 4. 計分與驗收

* Q1、Q2、Q3 設參考答案（由 `batch_compute` 輸出可機械驗證）；Q4、Q5 為主觀。
* 客觀題（Q1~Q3）正確率 ≥ 80% 視為通過 SC-005。
* Q5 收集到的「困惑點」進入 viz 後續迭代 backlog；非本 phase 必修。

## 5. 結果記錄

每次受試後將原始答題卡掃描存入 `docs/visual_review/<YYYY-MM-DD>_<受試者代號>.pdf`，
並在 `docs/visual_review/results.md` 增加一列：

```markdown
| 日期 | 受試者代號 | 背景 | Q1~Q3 客觀分 | Q4 | Q5 摘要 |
|------|------------|------|--------------|----|---------|
```

達 3 人以上且客觀題綜合 ≥ 80% 後標記 SC-005 通過；於 PR 描述附上連結。
