# Feature Specification: PPO Live Tracking Dashboard

**Feature Branch**: `010-live-tracking-dashboard`
**Created**: 2026-05-08
**Status**: Draft
**Input**: User description: "把 007 戰情室 Overview 從『OOS 回測展示』轉為『每日真實 prediction tracking dashboard』當產品看待。模型每天根據最新股價＋指標出 portfolio 決策，累積成 live_tracking.json artefact，前端顯示淨值 (NAV)、最大回撤 (MDD)、資產權重分配、reward 拆解（累積）、SMC 事件流。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 操作者手動觸發每日決策更新並看到最新淨值 (Priority: P1)

身為一個產品擁有者（同時也是研究者本人），打開 War Room Overview 頁面，要能立刻看到「今天為止」這個 PPO 策略累積跑出來的真實淨值曲線、回撤、最新一日的資產權重分配與 SMC 結構訊號。如果資料不是最新（例如距離今天已經超過一個交易日），我要能按下一個按鈕「手動更新到最新」，系統會自動補齊從上次更新到今天之間的所有缺漏交易日，更新完畢後畫面要重整顯示新的數據。

**Why this priority**: 這是整個 feature 的存在理由。沒有這個 user story，Overview 就還是停留在 OOS 回測快照展示，看不出「策略今天怎麼想」。所有其他 story 都是這個的支撐。

**Independent Test**: 在乾淨環境（無既有 live_tracking artefact）打開 Overview 頁，點「手動更新到最新」按鈕；等待 pipeline 跑完後，畫面 NAV 線出現至少一個新數據點（日期 = 2026-04-29 起算到當日 today），權重圖、reward 拆解、SMC overlay 全部反映該日決策。整段流程不需要重啟服務或手動跑 script。

**Acceptance Scenarios**:

1. **Given** Live tracking artefact 不存在（首次啟動），**When** 操作者在 Overview 頁按下「手動更新到最新」，**Then** 系統開始建立 artefact、跑從 2026-04-29 到 today 的每個交易日的 PPO 推論，並在完成後讓 Overview 顯示完整 NAV 曲線、權重圖、SMC overlay 與 reward 拆解。
2. **Given** Live tracking artefact 已經存在且最後一筆資料是 N 個日曆日前，**When** 操作者按下「手動更新到最新」，**Then** 系統補齊 last_frame.date+1 到 today 之間所有交易日的 frame、整段 SMC overlay 重算，畫面重整後 NAV 線新增 N 個資料點（已扣除非交易日）。
3. **Given** Live tracking artefact 已經是今日資料，**When** 操作者按下「手動更新到最新」，**Then** 系統判斷無事可做，立即回應「已是最新」並結束，畫面不變。
4. **Given** 操作者按下「手動更新到最新」之後 pipeline 仍在跑，**When** 操作者再次按下同一按鈕，**Then** 系統回應「正在更新中」並拒絕第二次觸發；按鈕呈現 disabled 或 spinner 狀態。
5. **Given** Overview 頁第一次載入，**When** 頁面渲染，**Then** 頁面 header 區域顯示一個「資料截至 N 天前」的徽章（基於 today − last_frame_date 的日曆天數），讓操作者一眼看出新鮮度。

---

### User Story 2 - 學術 baseline 與每日營運資料並存 (Priority: P2)

身為這個研究的撰寫人，我必須持續保有「OOS 回測快照」作為論文與簡報引用的不可變學術基準。同時我要有「Live tracking」作為每日營運的活成果。兩者都要從同一個 episodes 列表能存取，UI 載入體驗一致，但 OOS 那筆永遠不會被改寫。

**Why this priority**: Constitution Principle I（Reproducibility）對學術 baseline 是 NON-NEGOTIABLE。如果只有 mutable live tracking、丟掉 OOS，論文 repro 就崩了。但若沒有 live tracking，產品意義又消失。兩者必須共存。

**Independent Test**: GET /api/v1/episodes 回傳清單應含兩筆：一筆 OOS（id 包含 seed42 既有命名）、一筆 Live（id 對應 live tracking artefact）。從前端 EpisodeList 點 OOS 那一筆能看到 2026-04-28 截止的固定數據；點 Live 那一筆會切換到上一個 user story 的即時資料。OOS 那一筆任何時候重抓內容都應該完全一樣（內容 hash 不變）。

**Acceptance Scenarios**:

1. **Given** Live tracking artefact 已建立，**When** 操作者打開 EpisodeList，**Then** 列表顯示恰好 2 筆 episode（OOS + Live），各自標明來源類型。
2. **Given** 操作者點選 OOS 那筆 episode，**When** 系統回傳 detail，**Then** 內容固定為 2026-04-28 截止的 329 frames，不受 Live tracking 重整影響。
3. **Given** 操作者點選 Live 那筆 episode，**When** 系統回傳 detail，**Then** 回傳當前 live_tracking.json 全部內容（隨每次 refresh 變動）。
4. **Given** Live tracking artefact 不存在，**When** 操作者打開 EpisodeList，**Then** 列表顯示恰好 1 筆 OOS episode（Live 那筆暫不出現），Overview 頁則提示「Live tracking 尚未啟動，請按手動更新建立」。

---

### User Story 3 - Pipeline 失敗時不破壞既有資料、且失敗訊息能被使用者看到 (Priority: P2)

身為操作者，我按下「手動更新到最新」之後若中途有東西出錯（例如資料源拿不到當天 OHLCV、磁碟滿、模型載入失敗），我希望既有的 live_tracking 資料完全不受影響（昨天的 NAV 還在），同時前端要能告訴我「為什麼失敗」、「卡在哪一步」，讓我可以人工介入或等一下重試。

**Why this priority**: 失敗回滾與錯誤可見性是「當產品看待」的最低標準。若 pipeline 失敗會丟掉昨天的資料、或失敗只在後端 log 看不到，這個產品就沒有信任度。

**Independent Test**: 模擬資料源不可用（例如關掉 yfinance 網路或刪掉一筆 OHLCV）→ 按下手動更新 → 確認 live_tracking.json 內容仍是失敗前的最後成功版本（hash 不變），同時前端 status 區塊顯示錯誤訊息（例如「2026-05-08 資料抓取失敗：xxxxx」）。

**Acceptance Scenarios**:

1. **Given** Pipeline 處理到第 3 個缺漏日時拋例外，**When** 系統處理失敗，**Then** live_tracking.json 內容完全保留之前最後一次成功的狀態，操作者重整 Overview 看不到「半成品」。
2. **Given** Pipeline 失敗，**When** 操作者打開 Overview，**Then** 頁面顯示「上次更新失敗」的提示，包含失敗時間、失敗原因摘要、與「再試一次」按鈕。
3. **Given** Pipeline 失敗訊息已顯示，**When** 操作者按「再試一次」並且這次成功，**Then** 失敗提示消失、新資料被反映、status 標記為健康。

---

### Edge Cases

- **首次啟動且無歷史**：起始日 2026-04-29 是固定錨點。若 today < 2026-04-29（例如測試環境時間倒退），系統不應建立負區間，應回應「尚未到起始日」。
- **連假 / 週末整段都不是交易日**：last_frame.date 與 today 之間只有非交易日（例如週六按更新，上次是週五），補齊邏輯應正確跳過、不新增任何 frame，並回報「無新資料」而非錯誤。
- **資料源回缺值或部分資產缺資料**：當天某個資產（例如 NVDA）在資料源無 close 報價，pipeline 應回滾整批當日 frame（不部分寫入），並把該日標記為「資料不完整」。
- **多次同時按按鈕**：兩個並發 refresh 請求，第二個應立即被拒絕並回報「正在更新中」，而非排隊或重複跑。
- **長假期後一次補一週**：last_frame.date 與 today 之間有 5 個交易日缺漏，pipeline 應一次補完並只在最後做一次原子寫入；如果中途失敗，整批回滾不留半成品。
- **OOS 資料 id 與 Live id 衝突**：兩個 id 不得相同，命名規則必須能區分（例如 Live id 帶 `_live` 後綴）。
- **使用者離開頁面後 pipeline 還在跑**：pipeline 不依賴前端視窗存活，使用者下次回來看到狀態同步即可。
- **磁碟寫入到一半斷電**：原子寫入策略必須保證 live_tracking.json 要嘛是舊版要嘛是新版，不會出現破損 JSON。

## Requirements *(mandatory)*

### Functional Requirements

#### Live Tracking Artefact

- **FR-001**: 系統 MUST 維護一份名為 Live Tracking 的可變動資料快照，內含與既有 OOS Episode 相同 schema 的所有欄位（summary metrics、trajectoryInline frame 序列、reward 拆解、SMC overlay、per-asset OHLC）。
- **FR-002**: Live Tracking 快照的起始 frame 對應的交易日 MUST 為 2026-04-29（OOS 結束日 2026-04-28 的下一個美股交易日），起始 NAV 與 OOS 終值 1.7291986 銜接。
- **FR-003**: Live Tracking 快照中的 frame 序列 MUST append-only：歷史 frame 一旦寫入就不可被改寫，每次更新只能在尾端新增 frame。
- **FR-004**: Live Tracking 快照中的 SMC overlay 與 summary metrics（finalNav / cumulativeReturn / maxDrawdown / sharpeRatio / sortinoRatio）MUST 在每次更新後對整段（含歷史 frame）重新計算，因為新一筆資料可能令過去的 swing / FVG / OB 生命週期狀態翻轉。

#### Daily Pipeline 觸發

- **FR-005**: 系統 MUST 提供一個由使用者手動觸發的「更新至最新」入口（位於 Overview 頁 header），不依賴排程或自動 cron。
- **FR-006**: 系統 MUST 拒絕並發觸發：當前一個更新還在進行時，第二次觸發 MUST 立即回應「正在更新中」（不排隊、不重跑）。
- **FR-007**: 系統 MUST 在每次手動更新時，自動補齊 last_frame.date+1 到 today 之間所有美股交易日（跳過週末與假日）的 frame，無需使用者逐日操作。
- **FR-008**: 若 last_frame.date+1 > today（即已是最新），系統 MUST 立即結束該次更新並回報「已是最新」狀態。

#### 失敗處理

- **FR-009**: 系統 MUST 採原子覆寫策略寫入 Live Tracking 快照：寫入過程中發生任何錯誤（資料源抓取失敗、推論例外、磁碟 I/O 失敗），既有快照內容 MUST 保持上次成功狀態，不出現半成品或破損檔案。
- **FR-010**: 系統 MUST 記錄上次更新的成敗狀態：若失敗，記錄失敗時間、失敗階段、失敗訊息摘要，供使用者查看。
- **FR-011**: 系統 MUST 在使用者觸發更新後若失敗，於下次成功更新前持續對前端暴露「上次失敗」狀態，不靜默吞錯。

#### Episode 列表與細節 endpoint

- **FR-012**: 系統 MUST 在「取得所有 episodes 清單」的回應中同時包含 OOS 與 Live 兩筆 episode（若 Live artefact 已建立），並用 id 與 metadata 區分兩者來源。
- **FR-013**: 系統 MUST 在「取得單一 episode 細節」endpoint 接受 Live 那筆的 id 並回傳 Live Tracking 快照當前內容；同時對 OOS id 仍回傳 OOS 既有不可變快照。
- **FR-014**: 系統 MUST 對 OOS episode 細節保持回應內容跨多次請求穩定（無附帶時間戳、無變動欄位），以維持學術 baseline 可重現性；Live episode 細節則允許隨更新變動。

#### 狀態 endpoint 與更新觸發 endpoint

- **FR-015**: 系統 MUST 提供「Live Tracking 狀態」查詢入口，回傳至少：上次成功更新時間、最後一筆 frame 的日期、以日曆天為單位距離 today 的滯後天數、是否正在執行更新、上次失敗訊息（若有）。
- **FR-016**: 系統 MUST 提供「觸發 Live Tracking 更新」入口，立即回應已接受指令（不等待 pipeline 完成），同時提供預估完成時間，讓前端可開始輪詢狀態。

#### Gateway 反向代理

- **FR-017**: 系統 MUST 在 API gateway 暴露上述兩個 Live 入口（狀態查詢、更新觸發）給前端，與既有 episodes 入口維持相同 URL prefix 慣例。
- **FR-018**: 系統 MUST 對 Gateway 暴露的 Live 入口提供契約測試，確保 schema 與後端 inference service 一致。

#### Reward 與推論計算

- **FR-019**: 系統 MUST 在每日 pipeline 內呼叫與既有訓練／OOS 評估完全相同的 reward 函式（return − drawdown_penalty − cost_penalty），不得新增變體或近似實作。
- **FR-020**: 系統 MUST 使用既有已部署的 PPO policy（不重訓、不切換）做每日推論，輸出與 OOS evaluator 相同的 action 結構（raw / normalized / log_prob / entropy）。

#### 前端 Overview 整合

- **FR-021**: Overview 頁預設 episode 來源 MUST 切換為 Live Tracking（而非 OOS）：第一次載入時自動讀取 Live episode 細節並渲染；若 Live artefact 尚未建立，畫面 MUST 顯示「Live tracking 尚未啟動，請按手動更新建立」的引導提示。
- **FR-022**: Overview 頁 header MUST 顯示「資料截至 N 天前」徽章，N 為 today − last_frame.date 的日曆天數；當 N = 0 顯示「最新」。
- **FR-023**: Overview 頁 header MUST 提供「手動更新到最新」按鈕；按下後前端 MUST 對更新觸發 endpoint 發送請求、進入輪詢狀態 endpoint 模式（每 N 秒一次），完成或失敗後重抓 episode detail 並更新畫面。
- **FR-024**: Overview 頁 MUST 在更新進行中將按鈕改為 disabled / loading 狀態，避免使用者重複觸發。
- **FR-025**: 若 Live Tracking 上次更新狀態為失敗，Overview 頁 MUST 顯示錯誤通知（包含失敗時間、失敗摘要），並提供「再試一次」入口。

#### 觀測性

- **FR-026**: 系統 MUST 對每次 pipeline 執行寫入結構化 log，至少包含：本次新增 frame 數、SMC overlay 重算耗時、整體 pipeline 耗時、最終成敗狀態。
- **FR-027**: 系統 MUST 透過 Live Tracking 狀態 endpoint 把資料滯後天數暴露給前端使用者（FR-022 的徽章來源）。

### Key Entities *(include if feature involves data)*

- **Live Tracking Artefact**：與既有 OOS Episode 同 schema 的可變動資料快照；持久化於檔案系統；支援整檔原子覆寫；隨每次手動更新增長 trajectory frame、重算 summary 與 SMC overlay。屬性：起始日（2026-04-29）、起始 NAV（1.7291986）、最新 frame 日期、最新 NAV、SMC overlay、reward 拆解。
- **Live Tracking Status**：描述 Live Tracking Artefact 當前健康度與時效性的中繼資訊，**不**儲存於 artefact 內部；屬性：上次成功更新時間（ISO timestamp）、最後一筆 frame 日期（YYYY-MM-DD）、資料滯後天數（整數，日曆天）、是否正在執行更新（布林）、上次失敗訊息（可空字串）。
- **Daily Tracker Pipeline**：把多個缺漏交易日轉成 Live Tracking 快照新增 frame 的處理流程；步驟：抓最新 OHLCV → 對每個缺漏日跑 PPO 推論 → 推進 NAV 與回撤 → append frame → 對整段重算 SMC overlay → 重算 summary metrics → 原子覆寫快照。執行模型：背景任務、單一執行（mutex 保護）、append-only。
- **Manual Refresh Trigger**：來自前端的 HTTP 請求；行為：擠壓進 mutex 排程，立即回應已接受、預估時間，不等 pipeline 完成；若已有任務在跑回應 conflict。
- **Episode List Item**：episodes 清單中每一項的描述資料；屬性：episode id、來源類型（OOS / Live）、起訖日期、最新 NAV、frame 數、是否可變動。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (Live artefact 建立)**：在 Live Tracking 不存在的乾淨環境，操作者點擊一次「手動更新到最新」，2026-04-29 起到 today 為止所有交易日的 frame 都 appear 在 Overview 的 NAV 線上，且 frame 數量 = 2026-04-29 至 today 的美股交易日數（可由獨立交易日曆驗證）。
- **SC-002 (補齊缺漏日)**：當 Live Tracking 最後一筆 frame 為 N 個交易日前，操作者觸發一次更新後，frame 數量恰好增加 N 筆，且日期序列在交易日層級連續（跳過非交易日）；操作者無需多次點擊。
- **SC-003 (狀態可見性)**：前端載入 Overview 時，header 徽章顯示的「資料截至 N 天前」中的 N 與 today − last_frame.date 日曆天數差一致；驗證範圍涵蓋 N = 0 / 1 / 3 / 7 等典型情境。
- **SC-004 (並發保護)**：兩個操作者（或前端 race condition）在同一秒按下手動更新，第二個請求在 1 秒內收到「正在更新中」的回應，且後端 pipeline 只執行一次。
- **SC-005 (失敗回滾)**：在資料源不可用情境下觸發更新，pipeline 失敗後 Live Tracking 內容（包含 frame 數、最新 NAV）與失敗前完全相同，可由更新前後的內容比較驗證。
- **SC-006 (使用者操作 → 視覺反饋時間)**：操作者按下「手動更新到最新」後，若僅缺一個交易日的資料，60 秒內看到新 frame 反映在 Overview 的 NAV 線、權重圖、SMC overlay；若缺多個交易日（≤ 7 個），180 秒內完成。
- **SC-007 (跨 OOS / Live 統一渲染)**：同一個 episode 細節 schema 同時可承載 OOS 與 Live，前端不需要對 episode 來源做任何條件分支即可正確渲染所有圖表（NAV / drawdown / 權重 / K-line + SMC / reward 拆解）。
- **SC-008 (學術 baseline 不可變)**：對 OOS episode 細節做連續 5 次內容讀取並計算 hash，所有 hash 相等；該 OOS episode hash 不受任何 Live Tracking 更新影響。
- **SC-009 (失敗訊息可見)**：在模擬失敗情境下，操作者重新整理 Overview 後 5 秒內看到失敗錯誤通知（包含失敗時間 / 失敗摘要 / 再試一次入口），不需查看後端 log。

## Assumptions

- 起始錨點 2026-04-29 為 OOS 結束日 2026-04-28 的下一個美股交易日；若該日恰為非交易日，將自動順延至最近下一個交易日。
- Live Tracking 起始 NAV 接續 OOS 終值（1.7291986），意義為「此策略從 OOS 結束後實盤跑下去到今天的累積成果」。
- 操作者為單一研究者本人 + 少數可被信任的 demo 觀眾；無多租戶、無權限分級需求。
- 無正式付費 SLA：每日資料延遲一天內為可接受體驗，不要求即時 streaming。
- 美股交易日曆採用 NYSE 標準（含 Federal holiday 與半日市），由現有資料 ingestion 模組（feature 002）的同一份交易日定義決定，不另起獨立曆。
- 部署環境：本地 docker compose 為 MVP 唯一目標環境；雲端 Zeabur 部署的儲存實作（檔案 vs 物件儲存）屬下個 feature 範疇。
- PPO policy 不會在 Live Tracking 期間更新；當未來重訓 policy 時 Live Tracking 將改用新 policy id 重新建立 artefact，舊 artefact 保留作為歷史紀錄（屬未來 feature）。
- Reward function 與 OOS 評估完全相同（return − drawdown_penalty − cost_penalty），不為 Live Tracking 引入變體（憲法 Principle III, NON-NEGOTIABLE）。
- 學術 baseline 的可重現性（憲法 Principle I, NON-NEGOTIABLE）僅約束 OOS Episode；Live Tracking 因每日新資料必然變動，**明確不**要求跨日內容雜湊一致。

## Out of Scope

- GitHub Actions 或其他自動排程：使用者明確採純手動觸發，本 feature 不寫任何 cron 或 workflow_dispatch 自動化。
- PPO 重訓：本 feature 沿用既有 policy，不新增訓練流程。
- 多 policy 並行 Live Tracking：本 feature 假設單一 active policy；若未來要追蹤多個 policy，屬另一 feature。
- 即時 streaming（盤中 tick-level 更新）：本 feature 採每日批次觸發。
- 歷史 prediction 修改：append-only，不允許改寫過去的 frame。
- 雲端部署具體配置（Zeabur 或其他平台的環境變數、儲存層、Domain 設定）：屬未來 deploy 階段，不在本 feature 範疇。
- Episode 列表分頁：當前最多 2 筆 episode，分頁屬未來需求。
- 多人協作衝突解決：操作者只有單一研究者本人，並發保護以 mutex 即可。

## Dependencies

- 既有 OOS Episode artefact（feature 009）作為 schema 與起始 NAV 的依據。
- 既有 PPO policy（feature 004 的 final_policy.zip）作為每日推論模型。
- 既有 SMC engine v2（feature 008）的 batch_compute_events 用於整段 SMC overlay 重算。
- 既有資料 ingestion（feature 002）作為每日 OHLCV 抓取來源與交易日曆來源。
- 既有 inference service（feature 005）作為新 endpoint 的容器。
- 既有 Spring Gateway（feature 006）作為前端的反向代理。
- 既有前端 War Room（feature 007）的 Overview 頁與 envelope mapper。
