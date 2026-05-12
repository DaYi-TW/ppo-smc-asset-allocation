# Phase 0 — Research: Live Tracking Dashboard

**Feature**: 010-live-tracking-dashboard
**Date**: 2026-05-08
**Status**: 全部解決，無未決 NEEDS CLARIFICATION

本文件解析 plan.md Technical Context 中的所有未知與技術選型。每節格式：**Decision** / **Rationale** / **Alternatives considered**。

---

## R1 — 原子寫入策略（跨 Linux + Windows）

**Decision**:
- 重用 `src/data_ingestion/atomic.py` 的 `staging_scope` + `atomic_publish` 模式：在 artefact 目錄下建立 `.staging-<UTC_TS>/` → 寫 `live_tracking.json` + `live_tracking_status.json` 進去 → 全部成功後 `os.replace()` 移到目標位置。
- 寫檔流程：`open(tmp, "w") → write → flush → os.fsync(fd) → close → os.replace(tmp, target) → os.fsync(parent_dir_fd)`（Linux）。Windows 上 `os.fsync(parent_dir_fd)` 不適用 — 略過該步驟，由 `os.replace` 自身的 atomic 性質擔保。
- 任何 exception → 整個 staging 目錄被 `staging_scope` context manager 清掉，不留半成品。
- lifespan 啟動時掃描 `LIVE_ARTEFACT_DIR` 下殘留 `.staging-*` 目錄與 `.tmp` 檔，刪除。

**Rationale**:
- `atomic.py` 已在 feature 002 ingestion 模組驗證過，含 Windows-friendly 錯誤訊息（`PermissionError` → 提示關掉 Excel/Explorer），重用減少維護面。
- `os.replace` 在 POSIX 是 atomic（rename(2)），在 Windows NTFS 同卷時也是 atomic（MoveFileExW + MOVEFILE_REPLACE_EXISTING）；跨卷不適用，但本 feature 的 staging 與 target 在同目錄 → 同卷保證。
- Pipeline 同時要寫兩個檔（artefact + status），用 staging dir 一次 commit 比兩次 os.replace 更乾淨：避免「artefact 寫好但 status 沒更新」的中間狀態。

**Alternatives considered**:
- **直接 `tmp + os.replace` 不用 staging dir**：簡單但兩個檔同步性弱（artefact 成功 / status 失敗會留下不一致）。
- **SQLite WAL**：跨檔 atomicity 強但引入 schema migration 與資料庫運維成本，違反「單檔 mutable」設計初衷。
- **POSIX `rename(2)` 直呼**：Python `os.replace` 已封裝，無理由跳過。

---

## R2 — NYSE 交易日曆來源

**Decision**:
- 使用 `pandas_market_calendars` 套件：`pandas_market_calendars.get_calendar("NYSE").schedule(start_date, end_date)` 拿到 DataFrame，索引就是交易日。
- 封裝在 `src/live_tracking/calendar.py` 純函數 `missing_trading_days(last_frame_date: date, today: date) -> list[date]`，回傳 `(last_frame_date, today]` 區間（左開右閉）內所有交易日。
- 對 today 為非交易日的處理：依然回傳 `(last_frame_date, today]` 內的交易日；today 不交易則最大值是 today 之前的最近交易日。
- 對 last_frame_date == today 的處理：回傳空 list（no-op）。

**Rationale**:
- `pandas_market_calendars` 是業界標準（Quantopian、zipline-reloaded、backtrader 等都用），含 NYSE Federal holiday、Good Friday、半日市清單，每年由維護者更新。
- 純函數可獨立單測，不依賴 IO；calendar.py 不引入額外 cache。
- Python 3.11 wheel 無 native 依賴（純 Python + pandas）；docker image 體積影響 < 1 MB。

**Alternatives considered**:
- **手寫 NYSE holiday 表**：每年要人工同步 Federal Reserve holiday list；半日市規則複雜（Black Friday、Christmas Eve）；長期維護成本不划算。
- **`pandas.tseries.offsets.BDay`**：只跳週末，不跳國定假日；對美股不適用（會漏跳 Independence Day、Thanksgiving 等）。
- **`exchange_calendars`**（`pandas_market_calendars` 的 fork）：API 略不同，社群活躍度相當；選擇 `pandas_market_calendars` 因為既有專案 pip 生態更熟悉。

---

## R3 — Single-step env 推進策略

**Decision**:
- pipeline 內每個 missing day 跑：
  1. 從 store 拿 `last_frame.weights` 與 `last_frame.nav` 作為當前 portfolio state。
  2. 從資料 ingestion 拿當日 OHLCV → 餵給 `PortfolioEnv` 構造當日 observation（含 SMC signals）。
  3. 呼叫 `policy.predict(obs, deterministic=True)` 拿 action（含 raw / normalized / log_prob / entropy）。
  4. 呼叫 `env.step(action)` 推進 NAV、扣交易成本、計算 reward 三元。
  5. 從 `info["reward_components"]` 與 `info["smc_signals"]` 取結構化欄位，組成 `Frame` append 到 envelope。
- env 不需要從 episode 起點 reset；pipeline 維護自己的 `(weights, nav, drawdown_max)` state 並 inject 進 env 的 internal counters。
- **絕對不**自寫 NAV 推進邏輯。reward 計算必須由 env 內部 reward function 執行（Principle III gate）。

**Rationale**:
- Constitution Principle III NON-NEGOTIABLE 強制 reward function 不變。pipeline 若自寫 NAV / reward 計算就違反該原則。
- env.step 已是訓練/評估 / 預測的共用實作（feature 003 / 004 / 005 都走同一條），重用避免 logic drift。
- single-step 模式因為每天只跑一步，env 的 episode 結束邏輯（done / truncated）不會觸發；pipeline 直接忽略 done 旗標，把每日 step 當成「永續 episode」的一個 frame。

**Alternatives considered**:
- **重整個 OOS replay + N 個新 step**：成本高（每次 refresh 重跑 329 + N steps），且引入「OOS replay 結果可能漂移」風險（若 env 內隨機性、資料快照 update 則重跑結果不同）。否決。
- **手寫 NAV 推進**：違反 Principle III，否決。
- **跑一次 reset 後從 OOS 終點繼續 step**：env reset 必須給定起點 obs；OOS 終點與 Live 起點之間有時間斷層，env 內部 prev_obs / hidden state 不一致 → 否決。

---

## R4 — SMC overlay 全段重算 vs 增量

**Decision**:
- 每次 refresh 對 **整段** trajectory（OOS 終點起到最新一日）跑一次 6-asset `batch_compute_events`，覆蓋 `smcOverlayByAsset`。**不**做增量。
- 該決策 spec FR-004 已明確：「SMC overlay 與 summary metrics MUST 在每次更新後對整段（含歷史 frame）重新計算，因為新一筆資料可能令過去的 swing / FVG / OB 生命週期狀態翻轉。」

**Rationale**:
- SMC engine 的 swing / FVG / OB 生命週期會因新一筆資料 invalidate 過去狀態（例如新一筆 high 把過去的 swing high 變成 lower high → 觸發 CHoCh）。增量重算須重做相同邏輯，工程複雜度高且容易漂移。
- 性能可接受：6 assets × < 400 frames 在 008 engine 下 < 2 秒（已在 009 e2e 驗證 6 assets × 329 frames ≤ 1 秒）；MVP 累積規模預期 < 400 frames。
- 整段重算保證 SMC overlay 與當前 trajectory 完全一致，不會出現「部分 frame 用舊 swing 標記、部分用新」的視覺不連貫。

**Alternatives considered**:
- **增量重算**：只對新增 frames 加 swing / FVG / OB 評估 → 工程複雜度高，且要重做 008 engine 內部 `track_lifecycle` 邏輯（會 invalidate 既有 zone）；放棄。
- **不重算（只新增 zone）**：違反 FR-004，會出現過時的 active zones；放棄。

---

## R5 — Live id 命名與 EpisodeList 排序

**Decision**:
- Live id = `<policy_run_id>_live`（example：`20260506_004455_659b8eb_seed42_live`）；suffix `_live` 為唯一識別。
- OOS id 沿用既有命名（無 suffix）。
- `MultiSourceEpisodeStore.list_envelope()` 排序：OOS 在前（穩定學術錨點）、Live 在後（產品最新）。
- `MultiSourceEpisodeStore.get_envelope(id)` dispatch：id endswith `_live` → live store；否則 → OOS store。

**Rationale**:
- Suffix-based dispatch 簡單可測；與既有 OOS id 不衝突（OOS id 由 `git short hash + seed` 組成，永遠沒有 `_live`）。
- OOS 在前是 UX 選擇：使用者打開 EpisodeList 預期看到「學術 baseline」與「Live tracking」兩種來源；OOS 為穩定錨點，Live 為動態。前端 OverviewPage 預設選 Live 用 `defaultEpisodeId = lastSummary.id ?? firstSummary.id`（spec FR-021）。

**Alternatives considered**:
- **Live id = `<policy_run_id>` + Live 取代 OOS**：違反 spec FR-012（兩筆並存），否決。
- **UUID-based Live id**：每次重建 artefact UUID 變 → 前端要每次重抓 list；複雜化否決。
- **Sort by date**：兩筆 episode 起訖日重疊，無明確順序；放棄。

---

## R6 — Status 持久化策略 + 孤兒 lock 復原

**Decision**:
- Status 檔案 = `live_tracking_status.json`，與 artefact 同目錄。schema：
  ```json
  {
    "last_updated": "2026-05-08T14:00:00Z",
    "last_frame_date": "2026-05-07",
    "is_running": false,
    "last_error": null,
    "running_pid": null,
    "running_started_at": null
  }
  ```
- `is_running=true` 時必須同時設 `running_pid` 與 `running_started_at`，作為孤兒 lock 復原依據。
- 啟動時的 recovery 邏輯：
  1. 若 status 檔不存在 → 建立預設（`is_running=false`、`last_frame_date=null`）。
  2. 若 `is_running=true` 但 `running_pid` 不是當前 process 且該 PID 已不存在（`os.kill(pid, 0)` raises `ProcessLookupError` / Windows `psutil.pid_exists`）→ reset 為 `is_running=false` + `last_error="orphan_lock_recovered"`。
  3. 若 `is_running=true` 且 `running_started_at` 早於本 process startup_time → 同上 reset。
  4. 清理同目錄殘留 `.staging-*/` 與 `.tmp` 檔。

**Rationale**:
- `asyncio.Lock` 是 in-process mutex，process restart 後丟失；status 檔案是跨 process 的持久 mutex。
- PID + startup time 雙重確認避免 PID reuse 衝突。
- recovery 邏輯放 lifespan startup，FastAPI 啟動失敗 = uvicorn fail fast，不會偷偷帶著壞狀態跑。

**Alternatives considered**:
- **Redis SETNX**：依賴外部服務，本 feature 已 005 既有 Redis client 可用，但引入額外 fail mode（Redis 斷線時 lock 行為未定義）；單檔 mutex 已足夠。
- **`fcntl.flock`**：Linux only，跨平台問題；否決。
- **不持久化 is_running**：process restart 後若 pipeline 仍在跑（不可能，pipeline 隨 process die）→ 純假設，意義不大；持久化的價值在啟動時清理孤兒、不在跨 process 同步。

---

## R7 — Pipeline 失敗錯誤分類

**Decision**:
- 三類錯誤分類，記錄在 `status.last_error` 欄位字串前綴：
  - `DATA_FETCH:` — 資料源失敗（yfinance 網路、parquet schema 錯、缺資產欄位）
  - `INFERENCE:` — policy load / env step / single_step_inference 例外
  - `WRITE:` — 磁碟 I/O / atomic write / json 序列化失敗
- pipeline catch 各階段例外 → 套對應 prefix → re-raise 到 BackgroundTask 結束邏輯（在 FastAPI 內被吞，不影響 endpoint response，但寫進 structured log）。
- 前端從 `last_error` 字串前綴決定 toast 樣式（「資料源異常，建議稍後再試」/「模型推論異常，請通知開發者」/「儲存失敗，可能磁碟已滿」）。

**Rationale**:
- 失敗訊息給使用者需語意化分類；技術 stacktrace 對非開發者無價值。
- 三類分類涵蓋 pipeline 主要失敗點：資料、計算、IO。新類型（如未來加 Redis publish）可加新前綴而不破壞現有契約。
- 不引入專屬 error model（避免過度工程化）；字串前綴 + 後綴訊息已足夠。

**Alternatives considered**:
- **完整 error code enum**：強型別但前端要對應 i18n key；目前無 i18n 框架；放棄。
- **單純 stacktrace**：對使用者無意義；放棄。

---

## R8 — OOS + Live 雙來源 EpisodeStore 重構

**Decision**:
- 把既有 `EpisodeStore`（009 single-episode）重構為 `MultiSourceEpisodeStore`：
  ```python
  class MultiSourceEpisodeStore:
      def __init__(self, oos: OOSEpisodeStore | None, live: LiveTrackingStore | None): ...
      def list_envelope(self) -> EpisodeListEnvelope: ...
      def get_envelope(self, episode_id: str) -> EpisodeDetailEnvelope | None: ...
  ```
- `OOSEpisodeStore` = 現有 009 `EpisodeStore` rename（行為不變：lifespan eager load JSON → 記憶體 dict → list/get）。
- `LiveTrackingStore` = 新模組，每次 `list_envelope` / `get_envelope` 重讀檔（因為 mutable，不能 cache）；讀檔失敗 → 回 None（Live 暫不存在情境）。
- list 排序：OOS first（若有），Live second（若有）。
- get dispatch：id endswith `_live` → live；否則 → OOS；不匹配 → None。

**Rationale**:
- 重構而非新增 wrapper：避免「new store 包 old store」的洋蔥層；類別職責清晰。
- LiveTrackingStore 不 cache：因為前端輪詢 status 後可能立即抓 detail，cache 與 mutable 衝突；每次重讀檔成本可控（< 10 MB JSON、deserialize < 50 ms）。
- 缺一筆來源時 list 仍 functional（只回現有的）；FR-012 對 Live artefact 尚未建立的情境 fallback 為「只回 OOS」。

**Alternatives considered**:
- **保留 single store + 在 endpoint layer 拼湊兩份回應**：endpoint 邏輯複雜化；放棄。
- **LiveTrackingStore 也 eager load**：mutable artefact + eager load = stale cache；放棄。

---

## R9 — policy.zip 載入策略：pipeline 與既有 inference handler 共用

**Decision**:
- 重用 005 既有 lifespan-loaded policy（存於 `app.state.policy`，由 `Settings.POLICY_PATH` 指定）。
- pipeline 透過 dependency injection 接收 policy（不在 pipeline 內 reload）。
- `single_step_inference(policy, obs, env)` 函數簽章接收 policy 與 env 為參數，無 module-level globals。

**Rationale**:
- policy.zip 載入耗時（sb3 PPO 約 1~2 秒）；重用避免每次 refresh 都重 load。
- DI 模式利於測試（pytest fixture 給 mock policy）。
- 一個 policy 同時 serve `POST /infer/run`（既有）與 pipeline，無資源競爭（policy.predict 是純函數呼叫，無 mutable state）。

**Alternatives considered**:
- **pipeline 內獨立 reload**：浪費啟動時間 + 可能與 main service 用不同版 policy（race condition）；放棄。

---

## R10 — Backend pipeline 觸發機制（FastAPI BackgroundTasks vs 獨立 worker）

**Decision**:
- 使用 `FastAPI.BackgroundTasks`：endpoint handler 接到 POST → 立即 schedule pipeline 為 BackgroundTask → 回 202 + `RefreshAcceptedDto`。
- pipeline 在 FastAPI event loop 中執行；耗時 step（env.step / batch_compute_events）若 block event loop → 用 `asyncio.run_in_executor` 包進 thread pool。

**Rationale**:
- BackgroundTasks 是 FastAPI 內建，無新依賴；對單一 active policy 場景已足夠。
- 用 `run_in_executor` 處理 CPU-bound 步驟避免 block 其他 endpoint（health / status / OOS detail）。
- 不引入 Celery / RQ / Dramatiq 等 worker queue；本 feature 的 pipeline 為 60 秒級，single-flight，不需要分散式 queue。

**Alternatives considered**:
- **APScheduler**（005 既有 cron 機制）：用於 scheduled 觸發，本 feature 是 manual trigger，重用 cron 邏輯反而複雜；分開兩個機制各司其職。
- **獨立 worker process**：跨 process 通訊複雜，且本 feature 為 manual trigger 場景無分散式需求；放棄。

---

## R11 — Frontend polling 策略

**Decision**:
- React-Query `useQuery` for `GET /live/status`：
  - `refetchInterval`：當 `status.is_running === true` 時 3 秒一次；否則 60 秒一次（讓使用者重新打開頁面時也有相對新鮮的 lag 顯示）。
  - `refetchOnWindowFocus`: true（使用者切回 tab 時立即更新）。
- React-Query `useMutation` for `POST /live/refresh`：
  - `onSuccess` → invalidate `episode/<live_id>` query → 觸發重抓 detail。
  - `onError` → toast 顯示 `last_error` 分類訊息。
- Mutation 進行中（`isPending`）→ Button disabled + spinner；不依賴 status polling 來顯示 in-flight 狀態（因為 mutation 結果立即知道）。

**Rationale**:
- 分離 mutation in-flight 與 pipeline in-flight：mutation 只是「按鈕剛按下還沒收到 202」（< 500ms）；pipeline in-flight 是「202 之後 pipeline 還在跑」（< 60s）。前者用 React-Query 的 `isPending`，後者用 `status.is_running`。
- 3s 輪詢 in-flight 狀態：在 60s 上界內提供 ~20 次更新機會；網路成本可控（每次 < 1 KB）。
- 60s 閒置輪詢：保證使用者離開又回來時 lag badge 不會永遠停在舊值。

**Alternatives considered**:
- **WebSocket / SSE 推送 status**：實作複雜（需 005 加 SSE endpoint + 前端訂閱）；polling 已足夠，否決。
- **單純 mutation onSuccess refetch**：使用者離開頁面時 status badge 不更新；保留輪詢。

---

## R12 — Status 檔案的 last_updated 解釋

**Decision**:
- `last_updated` 紀錄 **上次成功 pipeline 完成的 UTC 時間戳**（pipeline raise 例外時 last_updated 不更新）。
- `last_frame_date` 紀錄 **artefact 中最新 frame 的交易日**（YYYY-MM-DD，不帶時區）。
- `data_lag_days` = `(today - last_frame_date).days`（純日曆天數，不扣假日）。

**Rationale**:
- 兩個欄位各代表不同事：「資料新鮮度」（frame_date）vs「上次成功動作時間」（updated）。把它們混為一談會誤導使用者（系統剛剛 refresh 但其實 today 是週末，frame_date 沒前進）。
- 日曆天計算最直觀：「3 天前」對非工程使用者可立即理解，比「2 個交易日前」更符合一般語感。

**Alternatives considered**:
- **lag 用交易日**：更精準但前端要載入 calendar 才能解讀；放棄。
- **單一欄位 last_updated**：失去「資料新鮮度」資訊；放棄。

---

## 總結

所有 12 項研究決議皆解決，無未決 NEEDS CLARIFICATION。Phase 1 可繼續展 data-model.md 與 contracts/。
