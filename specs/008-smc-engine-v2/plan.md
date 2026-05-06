# Implementation Plan: SMC Engine v2 — 規則化結構事件偵測

**Branch**: `008-smc-engine-v2` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-smc-engine-v2/spec.md`

## Summary

把 feature 001 落地的 SMC 引擎（`src/smc_features/`）從「逐根 K 棒信號 + swing-driven OB」重構為「結構化 event 列表 + dedup signal array + break-driven OB + ATR-filtered FVG」。技術手段：

1. 在 `types.py` 新增 `StructureBreak` dataclass、擴充 `OrderBlock` 加 `source_break_index/kind`、擴充 `SMCFeatureParams` 加 `fvg_min_atr_ratio`（預設 0.25）。
2. 在 `structure.py` 內維護 `used_swing_high / used_swing_low` 標記，第一次突破即發 event 並 mark used；同時收集 `list[StructureBreak]`。`bos_signal / choch_signal` int8 array 介面保留（dtype/shape 不變），但僅在 event 當下=±1。
3. 在 `ob.py` 改為 break-driven：移除 swing-marker 入口；新增 `build_obs_from_breaks(breaks, ...)`，每筆 break 往回找最後一根反向 K → 產生 OB（含 `source_break_index`）。OB 失效規則沿用 v1。
4. 在 `fvg.py` 偵測階段加入 ATR 過濾條件：`(top - bottom) / atr[i] >= fvg_min_atr_ratio`，ATR=NaN 時退化為僅檢 `fvg_min_pct`。
5. 在 `batch.py` 串接新順序：`swings → bos/choch+breaks → ob (吃 breaks) → fvg`，`BatchResult` 多回 `breaks: list[StructureBreak]`。
6. 在 `incremental.py` 鏡像同一規則（state 內維持 `used_*` 集合與 `pending_breaks` 列表，由前端逐根餵入時同步輸出 event）。
7. 在 `tests/{unit,contract}/` 補測試覆蓋新規則（BOS dedup、OB ↔ break 對齊、FVG ATR 過濾、event 物件欄位完整、incremental ↔ batch 等價）。

PPO env、observation shape、reward function **零改動**。重訓計畫屬於下一個 feature 範圍（標 out-of-scope）。

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: NumPy 2.x、pandas 2.x、pyarrow（沿用 feature 001/002 既有 lock）
**Storage**: 純函式庫，無 storage；上游從 `data/raw/*.parquet` 讀，下游餵 PPO env 與 fixture builder
**Testing**: pytest（既有 contract / unit / integration 三層）；coverage 目標 ≥ 90%（與 feature 001 對齊）
**Target Platform**: Linux container（Dockerfile pinned env）；macOS / Windows dev 透過 `docker compose run --rm dev`
**Project Type**: 單一 Python library（`src/smc_features/`）—— 不引入新 package
**Performance Goals**: 8 年 daily × 6 資產（2092 bars × 6） batch_compute < 2 秒；incremental 單 bar < 1 ms
**Constraints**: 介面相容（PPO observation 5 channel 不變、shape/dtype/NaN 慣例保留）；判定行為 deterministic（同輸入 byte-identical 輸出）
**Scale/Scope**: 約 6 個檔案修改 + 1 個新 dataclass；測試新增 ~10 個 case；無 schema migration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. 可重現性 (Reproducibility) — NON-NEGOTIABLE

- **Gate I-1（必過）**：`StructureBreak`、`OrderBlock`、`FairValueGap` 物件對於同一輸入必須產出相同欄位值（含 `bar_index` 與 `time` 雙欄位確保 timestamp 與位置一致）。
- **Gate I-2（必過）**：`incremental.py` 與 `batch.py` 對同一份 OHLCV 餵入，產出的 `breaks` 列表（順序、欄位、長度）必須完全相同。Phase 1 contract test 將以隨機 1000-bar 序列覆核。
- **Gate I-3（必過）**：dedup 狀態機（`used_swing_high/low`）的轉換規則必須可由 unit test 用最小可重現 fixture 完整覆蓋——不可有「依賴外部隨機性」的判定。
- **Gate I-4（必過）**：`fvg_min_atr_ratio` 預設 0.25 寫入 `SMCFeatureParams` 預設值；在 spec 與 plan 中標記為「初始值，可調 hyperparam」並列入未來 ablation 範圍——不允許 hardcode 數值。

### II. 特徵可解釋性 (Explainability)

- **Gate II-1（必過）**：每個新增/修改的演算法函式（dedup logic、OB break-driven 邏輯、FVG ATR 過濾）MUST 在 docstring 內以**規則文字 + 範例**雙形式描述判定條件（非僅程式碼）。
- **Gate II-2（必過）**：每條規則 MUST 至少一組正向 + 一組反向 unit test 覆蓋。例：BOS dedup → 「同 swing 第二次突破不發 event」反向 case。
- **Gate II-3（必過）**：v2 引擎輸出（`breaks` 列表）MUST 可被 War Room 視覺化覆核（feature 007 的 `smcOverlayPrimitive.ts` 已就緒，本 feature 提供的事件物件格式必須與其期待對齊）。

### III. 風險優先獎勵 (Risk-First Reward) — NON-NEGOTIABLE

- **Gate III-1（必過）**：本 feature **不修改 reward function**。`src/ppo_env/` 或同等模組未列入 scope；任何變更該檔的 PR 將被拒。
- **Gate III-2（必過）**：observation 的 5 個 SMC channel 維度、dtype、NaN 慣例不變；Phase 1 contract test 以「`batch_compute` 輸出仍能無轉換接入既有 PPO env」為驗收項。
- **Gate III-3（必過）**：v2 引擎輸出可能改變 PPO 訓練曲線（已知）；本 plan 的 out-of-scope 章節已標記「需重訓 + retune hyperparam」並列為下一個 feature。本 feature 完工驗收**不**以 PPO 訓練績效為準。

### IV. 微服務解耦 (Service Decoupling)

- **Gate IV-1（弱適用）**：本 feature 為純 Python 函式庫修改，不觸及 Java / Spring / Kafka / React 介面。**N/A** — 無需新增 contract。
- **Gate IV-2（必過）**：本 feature 產生的事件物件（`StructureBreak`）若未來需被 Spring Boot gateway 序列化轉發（feature 005/006 範疇），dataclass 欄位 MUST 全部 JSON-serializable（基本型別 + datetime/string）。本 plan 的 data-model.md 將驗證此點。

### V. 規格先行 (Spec-First) — NON-NEGOTIABLE

- **Gate V-1（必過，已通過）**：`specs/008-smc-engine-v2/spec.md` 已存在且通過 `requirements.md` checklist。
- **Gate V-2（必過）**：本 plan 文件 + Phase 1 產出（research.md、data-model.md、contracts/、quickstart.md）將與本 spec 對齊。任何在 implementation 階段發現的 spec 不足，MUST 回頭修正 spec 而非在程式碼私下決定。
- **Gate V-3（必過）**：所有 commit message 必須引用 task ID（`#23`–`#28`）或 FR 編號（`FR-XXX`）。

**Constitution Check 結論**：✅ **全綠通過**，無 violation。`Complexity Tracking` 區塊保留空白。

### Post-Design Re-evaluation（Phase 1 完成後）

於 research.md / data-model.md / contracts/ / quickstart.md 全部產出後，重新檢核五原則：

- **I. Reproducibility**：✅ Gate I-1～I-4 在 `data-model.md §2`、`contracts/batch_compute.contract.md Invariant B-7`、`contracts/incremental.contract.md Invariant I-1～I-5`、`research.md Decision 3` 中分別明文化。`SMCFeatureParams.fvg_min_atr_ratio = 0.25` 已寫入 default 而非 hardcode（Gate I-4）。
- **II. Explainability**：✅ `research.md` 含三個決策的規則文字描述；`quickstart.md Step 1` 列出 14 個 unit/contract test case，每條 FR 都有正反向 case 計畫（Gate II-2）。
- **III. Risk-First Reward**：✅ plan 的 Out-of-Scope 章節明文標記「不改 reward / 不改 PPO env」；contracts/batch_compute Invariant B-6 驗證 5 channel 介面 byte-相容（Gate III-1～III-3）。
- **IV. Service Decoupling**：✅ `contracts/structure_break.schema.json` 已驗證 JSON Schema 對齊；`data-model.md §7` 規範了序列化責任邊界（Gate IV-2）。本 feature 純 library 修改，不引入新跨層介面（Gate IV-1 N/A）。
- **V. Spec-First**：✅ Phase 1 全產物與 spec FR-001 ~ FR-015 對齊（Gate V-2）；implementation 階段如發現 spec 不足將回頭修 spec（Gate V-2 約定）。

**Re-check 結論**：✅ **後設計階段仍全綠**，可進 `/speckit.tasks`。

## Project Structure

### Documentation (this feature)

```text
specs/008-smc-engine-v2/
├── plan.md              # This file
├── spec.md              # Already created
├── research.md          # Phase 0 — 三個關鍵設計決策的研究結論
├── data-model.md        # Phase 1 — StructureBreak / OrderBlock(v2) / SMCFeatureParams(v2)
├── quickstart.md        # Phase 1 — 開發者本地驗證流程
├── contracts/
│   ├── batch_compute.contract.md     # batch_compute 輸入輸出契約（含 BatchResult 新欄位）
│   ├── incremental.contract.md       # IncrementalState ↔ batch 等價契約
│   └── structure_break.schema.json   # StructureBreak JSON Schema（為 Gate IV-2）
├── checklists/
│   └── requirements.md  # Already created — spec 階段 quality gate
└── tasks.md             # Phase 2 — 由 /speckit.tasks 產出
```

### Source Code (repository root)

```text
src/smc_features/
├── __init__.py             # 對外 export（新增 StructureBreak）
├── types.py                # ★ 修改：加 StructureBreak、擴 OrderBlock、擴 SMCFeatureParams
├── swing.py                # 不修改（FR-001 — 保留 v1 行為）
├── structure.py            # ★ 修改：dedup + 回傳 list[StructureBreak]
├── ob.py                   # ★ 重寫：移除 swing-driven，改 break-driven
├── fvg.py                  # ★ 修改：加 ATR 過濾入口
├── atr.py                  # 不修改
├── batch.py                # ★ 修改：串接新順序，BatchResult 加 breaks 欄位
├── incremental.py          # ★ 修改：state 加 used_swing 集合與 pending breaks
├── README.md               # ★ 修改：v2 行為文件
└── viz/                    # 不修改

tests/
├── unit/
│   ├── test_structure.py        # ★ 擴：dedup case、初始 BOS、CHoCh 優先
│   ├── test_ob.py               # ★ 重寫：break-driven case，移除 swing-driven 期望
│   ├── test_fvg.py              # ★ 擴：ATR 過濾邊界 case
│   ├── test_batch.py            # ★ 擴：BatchResult.breaks 欄位、順序穩定
│   └── test_incremental.py      # ★ 擴：incremental ↔ batch 等價
├── contract/
│   ├── test_smc_observation.py  # ★ 新：5 channel 介面相容性（FR-013）
│   └── test_event_schema.py     # ★ 新：StructureBreak 欄位完整 + JSON schema 對齊
└── integration/
    └── test_smc_pipeline.py     # ★ 擴：跨資產 6 標的 batch + 視覺密度 sanity
```

**Structure Decision**: 沿用既有 single-project layout（`src/smc_features/` + `tests/{unit,contract,integration}/`）。不新增 package，不重構目錄。所有改動鎖定在 SMC engine 模組與其測試——這降低 RL 訓練 retune 的耦合面（觀測介面不變、env 不變）。

## Phase Sequencing（with Task ID 對應）

| Phase | 內容 | FR 對應 | Task ID | 預估 |
|---|---|---|---|---|
| **0** | research.md：三個設計決策研究結論 | — | — | 0.5 hr |
| **1a** | data-model.md：dataclass schema | FR-006/009/011 | — | 0.5 hr |
| **1b** | contracts/：3 個契約文件 | FR-013/014 | — | 1 hr |
| **1c** | quickstart.md：本地驗證指南 | — | — | 0.3 hr |
| **2** | types.py 改造 | FR-006/009 | #23 (front-load) | 0.5 hr |
| **3** | structure.py 改造（dedup + events） | FR-002 ~ FR-007 | #23 | 2 hr |
| **4** | ob.py 改 break-driven | FR-008 ~ FR-010 | #24 | 1.5 hr |
| **5** | fvg.py 加 ATR 過濾 | FR-011/012 | #25 | 1 hr |
| **6** | batch.py + incremental.py 串接 | FR-014 | #26 | 1.5 hr |
| **7** | 測試補強 | FR 全條 | #27 | 2 hr |
| **8** | （out-of-scope）fixture builder 簡化 + 重生 | — | #28（屬 007） | 0.5 hr |
| **9** | （out-of-scope）PPO 重訓 + retune | — | 下個 feature | TBD |

`/speckit.implement` 將依序執行 Phase 2–7。Phase 8 在 008 落地後由 feature 007 的 follow-up commit 處理；Phase 9 為新 feature。

## Risk Register

| 風險 | 影響 | 機率 | 緩解 |
|---|---|---|---|
| **incremental ↔ batch 不等價** | 訓練/前端結果不一致 → 違反 Gate I-2 | 中 | Phase 1b contract test 用同一序列雙路徑跑、逐欄位比對；Phase 7 加入 randomized 1000-bar 等價測試 |
| **ATR NaN 期間 FVG 過濾語意不明** | warmup 期 FVG 全失或全留，行為不可預期 | 中 | spec FR-011 已決議「ATR=NaN 退化為僅檢 fvg_min_pct」；Phase 5 unit test 必含此 case |
| **Neutral trend 初始 BOS 邊界** | 序列開頭第一個突破歸類錯誤（應算 BOS 還是 CHoCh？） | 低 | spec FR-005 + Edge Case 已決議「neutral 期第一次突破 = 初始 BOS、設定 trend、不發 CHoCh」；Phase 3 unit test 必含此 case |
| **Swing 與 break 同根 K 邊界** | 同根 K 同時被確認為 swing 又突破前 swing → 自我參照 | 低 | spec Edge Case 決議「先發 break event 再更新 last_swing_*」；Phase 3 unit test 必含此 case |
| **PPO 重訓績效低於 v1** | v2 規則導致 RL 收斂變差 | 中 | 出 scope；下一個 feature 處理 hyperparam retune（entropy_coef / clip_range）。本 feature 不被此風險阻塞 |
| **`SMCFeatureParams` 新欄位破壞既有呼叫** | feature 002 / fixture builder 直接 fail | 低 | `fvg_min_atr_ratio` 用 `field(default=0.25)`，dataclass 後置欄位；既有位置/關鍵字呼叫不受影響 |

## Out-of-Scope（明確排除）

- **PPO env / observation 改動**：本 feature **不**改 `src/ppo_env/` 或同等模組（如有）。即使 v2 引擎輸出更稀疏的 BOS signal，env 端不調整 normalization / clipping。
- **PPO 重訓與 hyperparam retune**：訓練曲線變化在已知範圍，但 retune 屬下一個 feature。
- **Fixture builder 簡化**：`apps/warroom/scripts/parquet_to_ohlc_fixture.py` 中目前的 `used_anchors` / `ob_used` 後處理 hack 應該在引擎 v2 落地後清掉，但屬於 feature 007 後續 commit，**不**屬於本 feature。
- **War Room 視覺改動**：`smcOverlayPrimitive.ts` 已能正確消費 v2 的 `StructureBreak` 結構（feature 007 已就緒），本 feature 不動前端。
- **Reward function 修訂**：第 III 條 NON-NEGOTIABLE，永久 out-of-scope（除非走 constitution amendment）。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

（無 violations，本區塊留空。）
