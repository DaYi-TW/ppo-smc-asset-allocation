# Feature Specification: PPO Episode Detail Store

**Feature Branch**: `009-episode-detail-store`
**Created**: 2026-05-07
**Status**: Draft
**Input**: User description: "PPO Episode Detail Store — 把 OOS evaluator 跑出來的完整 trajectory（含 reward 拆解、action vector、SMC overlay、per-asset OHLC）持久化成可被 005 Inference Service 讀取的 episode artefact，並暴露 GET /api/v1/episodes 與 GET /api/v1/episodes/{id} 兩個 endpoint，讓 007 戰情室 Overview 頁可以直接讀真實 OOS 評估結果（不再依賴 mock fixture）。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 戰情室 Overview 顯示真實 OOS Episode (Priority: P1)

研究使用者打開戰情室 Overview 頁，期望看到的不是 mock fixture，而是這個 PPO policy 在 out-of-sample 期間（2025-01-02 → 2026-04-28，329 個交易日）的完整評估結果：KPI（final NAV、Sharpe、MDD）、NAV+drawdown 曲線、權重變化、6 檔資產 K 線+SMC overlay、每日 reward 拆解。整套來自單一可重現的 episode artefact，policy + 資料快照不變則結果 byte-identical。

**Why this priority**: 戰情室視覺化是這份論文的展示主軸；沒有真實 OOS 數據，所有圖都是假的，整個 demo 失去說服力。其他 user story 都依賴此 P1 提供的資料管線。

**Independent Test**: 在乾淨環境跑 `docker compose up`，從瀏覽器開 Overview 頁，畫面所有 panel（KPI bar、NAV+drawdown、權重 stacked area、K-line+SMC、SMC events、Reward sidebar）都顯示非空且非 mock 數值，且重啟容器後數值完全相同。

**Acceptance Scenarios**:

1. **Given** 一份已訓練的 PPO policy 與 OOS 資料快照，**When** 研究者執行評估流水線，**Then** 系統產出一份單一 episode artefact，內容涵蓋 329 frames 的 NAV、權重、reward 拆解、action vector、SMC signals、SMC overlay（6 檔）、per-asset OHLC（6 檔）。
2. **Given** episode artefact 已寫入 inference service 容器映像，**When** 戰情室前端呼叫 `GET /api/v1/episodes`，**Then** 收到一筆 episode summary（id、期間、final NAV、Sharpe、MDD、step 數）。
3. **Given** 上述 summary，**When** 前端呼叫 `GET /api/v1/episodes/{id}`，**Then** 收到完整 EpisodeDetailDto，可直接餵 Overview 頁所有圖表元件而不需 mock。
4. **Given** 同一 policy + 同一資料快照，**When** 重新跑評估流水線並重啟所有服務，**Then** 兩次產出的 episode artefact 在數值欄位上完全相同（憲法 Principle I：byte-identical reproducibility）。

---

### User Story 2 - 評估流水線輸出可下游消費的 Trajectory（Priority: P2）

研究者在離線環境跑完 PPO evaluator 後，產出的不再只是給 Colab notebook 用的精簡 CSV，而是一份結構化的 trajectory 檔（含 reward 拆解、action 細節、SMC signals），方便下游工具（artefact builder、其他研究腳本）直接讀取，不必逐欄重算。

**Why this priority**: P1 依賴 P2 把 reward 與 action 等欄位帶進來；但 P2 本身也對研究流程有獨立價值（後續做 reward shaping 分析、action 行為視覺化都可用）。

**Independent Test**: 在不啟動戰情室的情況下，研究者單獨跑 `python -m ppo_training.evaluate --policy <path> --save-trajectory`，產出的 trajectory 檔可被獨立腳本載入並驗證每列包含 reward total、return、drawdown_penalty、cost_penalty、action raw/normalized/log_prob/entropy、SMC bos/choch/fvg_distance_pct/ob_touching/ob_distance_ratio。

**Acceptance Scenarios**:

1. **Given** PPO policy 與 OOS 資料快照，**When** 研究者執行 evaluator 並啟用軌跡輸出，**Then** 產出檔案的每一列代表一個交易日，包含 NAV、log_return、weights、reward 四元拆解（total/return/drawdown_penalty/cost_penalty）、action 四元拆解（raw/normalized/log_prob/entropy）、SMC signals 五元（bos/choch/fvg_distance_pct/ob_touching/ob_distance_ratio）。
2. **Given** evaluator 已執行，**When** 比對新版 trajectory 中的 final_nav、累積報酬、Sharpe、MDD，**Then** 與 evaluator 同時輸出的 eval_summary 完全一致（同一 run、同一指標、同一數值）。
3. **Given** evaluator 已重跑，**When** 呼叫者請求向後相容 CSV，**Then** 仍可拿到精簡 CSV（date / nav / log_return / weights / closes）以避免破壞既有 Colab notebook。

---

### User Story 3 - Inference Service 暴露 Episode Read API（Priority: P3）

戰情室與其他外部工具透過 005 Inference Service 提供的 read-only API 取得 episode 資料；服務啟動時把映像內預先打包好的 episode artefact 載入記憶體並提供查詢，無需資料庫。

**Why this priority**: 是 P1 的傳遞層；但和 P1 解耦，因為 API 介面也可以被前端以外的工具（CLI、第三方 dashboard）使用。

**Independent Test**: 不啟動前端，只啟動 redis + 005 + 006，用 `curl` 對 Gateway 打 `GET /api/v1/episodes` 與 `GET /api/v1/episodes/{id}`，回傳的 JSON 通過 OpenAPI schema 驗證。

**Acceptance Scenarios**:

1. **Given** Inference Service 容器映像在 build time 已包含 episode artefact，**When** 服務啟動完成，**Then** 啟動 log 顯示 episode artefact 已載入，且 `GET /api/v1/episodes` 立即可用。
2. **Given** 服務啟動成功，**When** 客戶端請求列表 endpoint，**Then** 回傳格式為 envelope（含 items 陣列、meta），items 每筆為 EpisodeSummaryDto。
3. **Given** 客戶端取得某 id，**When** 請求對應詳情 endpoint，**Then** 回傳 EpisodeDetailDto，含 trajectoryInline 全部 frames、rewardBreakdown.byStep 與 cumulative、smcOverlayByAsset 6 檔、ohlcvByAsset 在每 frame 都是 6 檔。
4. **Given** 不存在的 id，**When** 客戶端請求詳情 endpoint，**Then** 回傳 HTTP 404 並附帶可解讀的錯誤訊息（ApiErrorViewModel schema）。

---

### Edge Cases

- 若映像 build 時 episode artefact 缺檔，服務啟動須以可診斷的訊息失敗（fail fast），不可在 request 時才報錯。
- 若映像同時含舊 mock fixture 與真實 artefact，服務必須以真實 artefact 為準，且 startup log 須明示來源。
- 若 evaluator 在 reward 元件取值失敗（例如 step info 缺欄位），須中止輸出而非寫出半完整 trajectory。
- 若 episode_id 包含 URL-unsafe 字元，API 層必須以 404 回應而非 500。
- 若 frontend 拿到的 trajectoryInline 與 rewardBreakdown.byStep 長度不一致，視為破損 artefact，UI 應顯示明確錯誤狀態。
- 多次評估（同 policy 不同 seed）目前 MVP 只保留最新一份；舊份若需保留為 follow-up（不在範圍）。

## Requirements *(mandatory)*

### Functional Requirements

#### Trajectory 輸出（evaluator 端）

- **FR-001**: 評估流水線在啟用軌跡輸出時，MUST 為每個交易日寫出一筆 frame，包含日期、step、NAV、log_return、weights（NVDA/AMD/TSM/MU/GLD/TLT/CASH 共 7 維）。
- **FR-002**: 每個 frame MUST 包含 reward 四元拆解：total、return component、drawdown_penalty、cost_penalty；其中 total 與 (return − drawdown_penalty − cost_penalty) 之差須在 1e-9 容差內（與 viewmodels/reward.ts invariant 對齊）。
- **FR-003**: 每個 frame MUST 包含 action 四元拆解：raw（policy 直接輸出，未 softmax）、normalized（softmax 後 simplex 權重）、log_prob、entropy。
- **FR-004**: 每個 frame MUST 包含當日 SMC signals 五元：bos、choch、fvg_distance_pct、ob_touching、ob_distance_ratio。
- **FR-005**: 評估流水線 MUST 額外輸出向後相容的精簡 CSV（date / nav / log_return / weights / closes），以保障既有 Colab notebook 不破。
- **FR-006**: 評估流水線輸出的 final NAV、累積報酬、Sharpe、MDD MUST 與同一次執行寫出的 eval_summary 數值完全一致。

#### Episode Artefact 組裝

- **FR-007**: 系統 MUST 提供一個 episode artefact 組裝步驟，把 trajectory、eval_summary、SMC overlay（6 檔）、per-asset OHLC（6 檔）合併成單一 episode artefact 檔。
- **FR-008**: episode artefact MUST 為 inference service 可在啟動時直接讀取的格式（單檔、無需資料庫、無需網路依賴）。
- **FR-009**: episode artefact 的 SMC overlay MUST 由與戰情室前端相同邏輯的 SMC engine（feature 008-smc-engine-v2）批次計算，避免前後端規則漂移。
- **FR-010**: episode artefact 中每一個 frame MUST 含 6 檔資產的當日 OHLC（不只 close），對齊前端 ohlcvByAsset schema。
- **FR-011**: 同一 policy + 同一資料快照重跑 evaluator + artefact builder，產出的 artefact 數值欄位 MUST 完全相同（憲法 Principle I）。

#### Inference Service Read API

- **FR-012**: 005 Inference Service MUST 在啟動時載入容器映像中的 episode artefact 並把摘要保留在記憶體；artefact 缺檔須 fail fast 並輸出可診斷錯誤。
- **FR-013**: 005 Inference Service MUST 提供 `GET /api/v1/episodes`，回傳 envelope 結構（items + meta），items 為 EpisodeSummaryDto（id、期間、step 數、final NAV、Sharpe、MDD 等可用於列表的欄位）。
- **FR-014**: 005 Inference Service MUST 提供 `GET /api/v1/episodes/{id}`，回傳 EpisodeDetailDto，包含完整 trajectoryInline、rewardBreakdown（byStep + cumulative）、smcOverlayByAsset、ohlcvByAsset。
- **FR-015**: 兩個 endpoint 的回應 schema MUST 與 OpenAPI 契約檔對齊，且通過契約測試。
- **FR-016**: 不存在的 episode id MUST 回 HTTP 404，錯誤格式遵循 ApiErrorViewModel schema；MUST NOT 回 500 或在錯誤訊息洩露 server 內部路徑。

#### Spring Gateway Proxy

- **FR-017**: 006 Spring Gateway MUST 為兩個 episodes endpoint 提供 1:1 反向代理，且不在路徑/queryString 上加工。
- **FR-018**: 006 Spring Gateway 的 OpenAPI 描述檔 MUST 包含這兩個 endpoint，並通過契約測試（Spring → 005 連接驗證，含 happy path 與 404 case）。

#### 前端 envelope mapper

- **FR-019**: 戰情室前端 MUST 提供 envelope mapper（toEpisodeSummary / toEpisodeDetail），把 API 回傳的 envelope 映射到 EpisodeSummaryViewModel / EpisodeDetailViewModel；mapper 須有單元測試。
- **FR-020**: 戰情室 Overview 頁 MUST 使用真實 API 資料；MVP 範圍內 MUST NOT fallback 到 mock fixture（fixture 僅供 unit test 用）。

### Key Entities *(include if feature involves data)*

- **Episode Artefact**: 一個 OOS 評估 run 的完整 episode；屬性包含 id（run_id 或對應字串）、policy 識別、期間、步數、KPI 摘要、frames（時間序列）、SMC overlays（per-asset）、per-asset OHLC。
- **Trajectory Frame**: episode 的一個交易日；屬性包含 timestamp、step、weights（含 cash bucket）、NAV、drawdownPct、reward 四元、action 四元、SMC signals 五元、ohlcv（per-asset）。
- **Reward Snapshot**: 單一 frame 的 reward 拆解；total / returnComponent / drawdownPenalty / costPenalty 滿足 invariant total ≈ return − drawdown − cost。
- **Action Vector**: 一次 policy 輸出的完整描述；raw（pre-softmax 7 維）、normalized（simplex 7 維）、log_prob、entropy。
- **SMC Signals (per frame)**: 該交易日的瞬時 SMC 觀測；bos、choch、fvg_distance_pct、ob_touching、ob_distance_ratio。
- **SMC Overlay (per asset)**: 跨整段 episode 萃取出的可繪事件；swings、zigzag、fvgs、obs、breaks。
- **Episode Summary**: 用於列表頁的精簡描述；id、期間、step 數、final NAV、cumulative_return、annualized_return、MDD、Sharpe、Sortino。
- **Episode Detail**: 列表中一筆的完整內容；summary 加上 trajectoryInline、rewardBreakdown（byStep + cumulative）、smcOverlayByAsset、ohlcvByAsset。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 在乾淨環境執行 `docker compose up` 後，戰情室 Overview 頁載入 5 秒內顯示完整 KPI 與所有圖表（NAV+drawdown / 權重 stacked area / 6 檔 K-line+SMC / SMC events / Reward sidebar），所有面板皆顯示真實 OOS 數值（非 mock）。
- **SC-002**: `GET /api/v1/episodes` 回傳 1 筆 episode summary，且其 final NAV、Sharpe、MDD、step 數與 evaluator eval_summary 數值完全一致。
- **SC-003**: `GET /api/v1/episodes/{id}` 回傳的 detail 中，trajectoryInline 與 rewardBreakdown.byStep 長度均為 329（OOS 期間 step 數），smcOverlayByAsset 含 NVDA/AMD/TSM/MU/GLD/TLT 6 個 key，ohlcvByAsset 在每個 frame 都包含 6 個 key 且每個 OHLCV 物件 4 個價格欄位皆非缺值。
- **SC-004**: 同一 policy + 同一資料快照重跑 evaluator + artefact builder + 重啟 inference service 兩次，兩次 `GET /api/v1/episodes/{id}` 的 JSON 在數值欄位 byte-identical（容差 0；憲法 Principle I）。
- **SC-005**: Inference Service 啟動時若映像缺 episode artefact，必在 30 秒內以非零 exit code 終止並在 log 印出可診斷訊息（不允許「啟動成功但 endpoint 永遠 404」）。
- **SC-006**: 006 Spring Gateway 對應 endpoint 的契約測試（含 happy path 與 404 case）100% 通過；OpenAPI lint 無 error。
- **SC-007**: 前端 envelope mapper 單元測試 100% 通過；對於缺欄位的 payload 測試案例，mapper 能拋出可識別的 schema-violation 錯誤而非靜默回傳壞資料。

## Assumptions

- 本 feature 使用既有已訓練的 PPO policy（`runs/20260506_004455_659b8eb_seed42`），不重訓。
- OOS 期間（2025-01-02 → 2026-04-28，329 個交易日）以及 6 檔資產定義（NVDA/AMD/TSM/MU/GLD/TLT）保持與 002-data-ingestion 一致。
- MVP 僅保留一份最新 OOS episode artefact 在 inference service 映像內；多 episode 列表、保留歷史 run 為 follow-up。
- Inference Service 不需資料庫；artefact 在 image build 時以唯讀檔案方式打包進去。
- 005 已具備 FastAPI app、健康檢查、Redis publisher（feature 005-inference-service）；本 feature 在其上新增兩個 read endpoint。
- 006 Spring Gateway 已具 OpenAPI lint 與契約測試骨架（feature 006-spring-gateway）；本 feature 補新 endpoint。
- 前端 EpisodeDetailViewModel / TrajectoryFrame / RewardSnapshot / SMCOverlay schema 已定型於 `apps/warroom/src/viewmodels/`；本 feature 不改 schema，只確認 mapper 對齊。
- SMC overlay 計算規則沿用 feature 008-smc-engine-v2；本 feature 不修改 SMC engine。
- Out of scope（明確排除）：重訓 PPO、training-loop dump、Episode CRUD（POST/PUT/DELETE）、多 episode 並存、前端 OverviewPage UI 重畫、多 policy 切換。
