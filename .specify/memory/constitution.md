<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR — 材料性調整 Technology Stack 章節既有原則的指引：
  將後端服務從「Java 17+ 搭配 Spring Boot 3.x」更新為「Java 25 (LTS) 搭配
  Spring Boot 4.x」。屬於擴充而非語意重新定義，未涉及任何 NON-NEGOTIABLE
  原則的範圍變更。

Modified principles: 無（五大原則內容皆未變動）

Added sections: 無

Removed sections: 無

Modified sections:
  - Technology Stack §後端服務 — Java 17+ → Java 25 (LTS)；
    Spring Boot 3.x → Spring Boot 4.x（2025 H2 GA，Spring Framework 7 / Jakarta EE 11）

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — 不受影響（Constitution Check 引用原則編號，未引用版本字串）。
  - ✅ .specify/templates/spec-template.md — 不受影響。
  - ✅ .specify/templates/tasks-template.md — 不受影響。
  - ✅ .specify/templates/checklist-template.md — 不受影響。
  - ✅ specs/001-smc-feature-engine/ — 不受影響（純 Python 函式庫，Constitution Check 第 IV 條為弱適用，未涉及 Java 版本）。
  - ⚠ docs/proposed_design.md / docs/related_work.md / docs/introduction_revised.md / README.md — 內文僅提「Spring Boot」未指定版本，無需修改；若未來新增章節提及版本號，請對齊本次新版本。
  - ⚠ 後端微服務 feature（尚未建立 spec）—— 未來新建立的 spec / plan MUST 採用本版本，並在自身 plan 的 Constitution Check 引用「Java 25 LTS + Spring Boot 4.x」。

Deferred TODOs: 無

Previous version history:
  - v1.0.0 (2026-04-29): Initial ratification. Replaced [PLACEHOLDER] template
    with five core principles (3 NON-NEGOTIABLE), Technology Stack,
    Development Workflow, and Governance sections.
-->

# PPO-SMC Asset Allocation Constitution

## Core Principles

### I. 可重現性 (Reproducibility) — NON-NEGOTIABLE

所有 RL 訓練、回測與評估流程 MUST 固定 random seed（含 Python、NumPy、PyTorch、Gymnasium
環境四層），並版本鎖定資料快照（資料來源、時間範圍起訖、欄位 schema、價格調整方式）。
完整超參數、環境版本、套件版本與硬體資訊 MUST 與每一次實驗結果同 commit 提交。

**驗收標準**：第三方檢出相同 commit 後，依 `quickstart.md` 步驟重新執行，所得回測淨值
曲線與績效指標（年化報酬、MDD、Sharpe）須在 1e-6 數值誤差內一致。

**理由**：金融 RL 結果對 seed 與資料切片極度敏感，缺乏可重現性的研究結論無學術或實務
價值，且無法支撐論文審查與實盤上線決策。

### II. 特徵可解釋性 (Explainability)

所有 SMC 特徵（BOS、CHoCh、FVG、OB 及其衍生量）MUST 滿足以下兩項：(1) 在 K 線圖上以
標記疊加方式視覺化呈現，使人工得以肉眼覆核演算法判定結果；(2) 特徵函數 MUST 於原始
碼註解或 docstring 中明列判定規則的數學定義，並附至少一組正面與一組反面單元測試案例。

**禁止事項**：不接受純黑箱數值輸出（例如「神經網路自學特徵」直接餵入觀測空間而無人類
可讀的中介定義）。

**理由**：本研究的核心貢獻是將 SMC 從主觀裁量轉為可量化特徵。若特徵本身不可解釋，論
文的 Related Work 第 3 節（彌補 SMC 量化研究缺口）即無法成立。

### III. 風險優先獎勵 (Risk-First Reward) — NON-NEGOTIABLE

PPO 的 reward function MUST 同時包含三個成分：(1) 階段性報酬、(2) 最大回撤 (MDD)
懲罰、(3) 交易成本與滑價懲罰。任何試圖以純報酬最大化（僅含成分 1）作為訓練目標的
PR MUST 被拒絕合併。

**變更規範**：任何修改三項權重、懲罰函數形式或新增 reward 成分的 PR，MUST 在對應
`plan.md` 中明列：（a）權重取捨的理由、（b）對歷史 baseline 實驗的回歸影響、
（c）是否觸發本原則的版本協商（見 Governance）。

**理由**：論文的 Findings 章節主張「兼具動態配置與風險控制」，若 reward 不含風險項，
模型將退化為純報酬追逐者，整個 SMC + PPO 框架失去差異化價值。

### IV. 微服務解耦 (Service Decoupling)

Python（AI 引擎）、Java/Spring Boot（API Gateway 與業務微服務）、React（戰情室前端）
三層 MUST 僅透過下列兩種介面溝通：(1) HTTP/HTTPS REST API、(2) Kafka topic 訊息。
**禁止**：跨層共享資料庫連線、共享行程內記憶體、共享檔案系統作為通訊媒介。

**獨立部署測試**：每個微服務 MUST 可在隔離環境（單機或單一容器）中啟動並通過自身的
contract test，不依賴其他兩層的 live instance。

**理由**：論文 Proposed Design 第 4 節以「消彌 AI 黑箱、企業級穩定」為號召；若三層
以行程內呼叫耦合，整個微服務架構主張在工程審查下不成立。

### V. 規格先行 (Spec-First) — NON-NEGOTIABLE

所有實作 MUST 先有 `specs/NNN-feature-name/spec.md` 並通過 `/speckit.specify` 後的
review gate，方可進入 `/speckit.plan`、`/speckit.tasks`、`/speckit.implement` 階段。
缺乏對應 spec 的程式碼變更（除排版、註解、文件修訂外）MUST 被拒絕合併。

**例外**：純文件變更（`docs/`、`README.md`、`CLAUDE.md`、`.specify/memory/`）與
建構腳本/設定檔（`.gitignore`、CI 設定）不適用本原則，但建議仍於 commit message
說明動機。

**理由**：本專案採 Spec-Driven Development（SDD），規格是 PR 審查、回歸測試與論文
撰寫的共同根據；繞過 spec 將使後續 `/speckit.analyze` 一致性檢查失效。

## Technology Stack

本節定義允許使用的技術選型範圍。任何擴增（新增語言、框架或主要套件）MUST 透過
constitution amendment 流程（見 Governance）。

- **AI 引擎**：Python 3.11+；核心套件 Gymnasium、Stable-Baselines3（或同等 PPO 實作）、
  pandas、NumPy、PyTorch。回測與資料處理優先採用 vectorized 寫法。
- **後端服務**：Java 25（LTS）搭配 Spring Boot 4.x（Spring Framework 7、Jakarta
  EE 11）；訊息中介使用 Apache Kafka；持久化優先選用 PostgreSQL。新建後端 feature
  之容器映像 MUST base on OpenJDK / Eclipse Temurin 25 LTS 或同等 25.x 發行版。
- **前端戰情室**：React 18+ 搭配 TypeScript；圖表函式庫 Recharts 或 D3；建構工具
  Vite 或同等現代 bundler。
- **跨層 contract**：REST API 以 OpenAPI 3.x 描述；Kafka 訊息以 JSON Schema 或
  Avro 描述。所有 contract MUST 置於對應 feature 的 `specs/NNN-*/contracts/`。

## Development Workflow

所有 feature MUST 依下列順序執行 Spec Kit 階段，跨階段的 review gate 不可跳過：

1. **`/speckit.specify`** → 產出 `spec.md`，定義 user scenarios、functional requirements、
   success criteria。
2. **Review gate**（人工）→ 確認需求完整、可測試、無歧義後方可進入 plan。
3. **`/speckit.plan`** → 產出 `plan.md`、`research.md`、`data-model.md`、
   `contracts/`、`quickstart.md`。Plan 中 MUST 包含 Constitution Check 區塊，逐條
   勾選本文件五大原則的合規狀態。
4. **Review gate**（人工）→ 確認 Constitution Check 全綠後方可進入 tasks。
5. **`/speckit.tasks`** → 產出 `tasks.md`，依 user story 分組並標註可平行任務。
6. **`/speckit.implement`** → 依 tasks 序執行；每完成一個 task 立即 commit。

跨 feature 平行開發允許，但同一 feature 內的階段順序不允許重排或跳躍。
`/speckit.clarify`、`/speckit.checklist`、`/speckit.analyze` 為輔助工具，可於主流程
任意階段插入使用。

## Governance

本 constitution 凌駕於本 repository 的所有其他開發實踐文件之上。當 CLAUDE.md、
`docs/`、PR 模板或 issue 模板與本文件牴觸時，以本文件為準。

**修改流程**：

1. 修改 constitution 的 PR MUST 在描述中明列：(a) 影響範圍（哪些既有 spec/plan/tasks
   需重審）、(b) 遷移計畫（既有未完成 feature 如何過渡）、(c) 版本號與 bump 理由。
2. 涉及 NON-NEGOTIABLE 原則（I、III、V）的修改 MUST 觸發完整 PR 審查；其餘原則與章節
   修改採一般 PR 流程。
3. 修改合併後，MUST 同步檢查並更新 `.specify/templates/` 下所有受影響範本。

**版本號規則（語意化版本）**：

- **MAJOR**：原則新增、移除或語意性重新定義（例如將 NON-NEGOTIABLE 降級）。
- **MINOR**：新增章節（例如新增 Security Requirements 章節）或材料性擴充既有原則
  的指引。
- **PATCH**：用詞修訂、錯字修正、不影響語意的格式調整。

**合規審查**：所有 PR 的 review 須驗證合規性；若 plan 含 Constitution Check 失敗項，
PR MUST 在 `Complexity Tracking` 區塊以「Violation / Why Needed / Simpler Alternative
Rejected Because」三欄記錄並取得審查者明確同意，否則不得合併。

**Version**: 1.1.0 | **Ratified**: 2026-04-29 | **Last Amended**: 2026-04-29
