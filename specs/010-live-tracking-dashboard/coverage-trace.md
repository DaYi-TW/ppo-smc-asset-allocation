# 010 — FR ↔ Tasks Coverage Trace

T067 deliverable per `tasks.md` Phase 7：每條 FR ≥ 1 task。本表由
`grep -E "FR-0XX" tasks.md` 自動產出後人工核對。

| FR | Tasks |
| --- | --- |
| FR-001 — Live artefact 同 schema | T002, T004, T010, T067 |
| FR-002 — 起始 frame = 2026-04-29 銜接 OOS 終值 | T003 |
| FR-003 — append-only frame 序列 | T007, T048 |
| FR-004 — 整段 SMC overlay + summary 重算 | T012, T019 |
| FR-005 — 手動觸發入口（無 cron） | T013, T020 |
| FR-006 — 並發 → 立即「正在更新中」 | T016, T025, T028 |
| FR-007 — 自動補齊缺漏交易日 | T001, T005, T008, T012, T017 |
| FR-008 — 已是最新 → 立即結束 | T012, T017 |
| FR-009 — 原子覆寫策略 | T007, T010, T012, T021, T052 |
| FR-010 — 記錄上次成敗與失敗階段 | T006, T009, T012, T053, T055 |
| FR-011 — 失敗訊息持續暴露至下次成功 | T006, T009, T056 |
| FR-012 — episodes list 含 OOS + Live | T025, T026, T027, T049 |
| FR-013 — episode detail 雙源 | T025, T026, T051 |
| FR-014 — OOS detail 跨請求穩定（學術 baseline） | T025, T047 |
| FR-015 — Live status endpoint 欄位 | T009, T027, T029 |
| FR-016 — refresh endpoint 202 + ETA | T025, T027, T028 |
| FR-017 — Gateway 暴露 2 入口 | T031, T034, T035 |
| FR-018 — Gateway 契約測試 | T024, T031, T036 |
| FR-019 — reward function parity（Constitution III） | T018, T060 |
| FR-020 — 既有 PPO policy 推論 | T011, T014, T018 |
| FR-021 — Overview 預設 Live | T046 |
| FR-022 — 「資料截至 N 天前」徽章 | T039, T044 |
| FR-023 — 「手動更新到最新」按鈕 | T045 |
| FR-024 — 進行中按鈕 disabled | T038, T040, T045 |
| FR-025 — 失敗通知 + 再試一次 | T045, T054, T056 |
| FR-026 — pipeline 結構化 log | T022 |
| FR-027 — 滯後天數暴露給前端 | T029, T067 |

## 缺漏盤點

掃描結果：27/27 FR 至少對應 1 task ✓。

## Constitution Gates 對應

| Principle | Gate item | Tasks |
| --- | --- | --- |
| I — Reproducibility (NON-NEGOTIABLE) | OOS episode_detail.json byte-identical（重抓 5 次 sha256 一致） | T047 |
| I — Reproducibility | Live artefact **明確不要求** byte-identical（spec FR-014 已聲明） | n/a（無 test） |
| II — Test-First | status / refresh 409 / 缺漏日 fixture 等 RED 測試早於實作 | T013, T015, T016, T024 |
| III — Risk-First Reward (NON-NEGOTIABLE) | daily pipeline 呼叫的 reward 必為 `portfolio_env.reward.compute_reward_components` | T018, T060 |
| IV — Observability | pipeline 寫 structured log（frames_appended / smc_zones_computed / pipeline_duration_ms / final_status）；status endpoint 暴露 data_lag_days | T022, T029 |
| V — Spec-First (NON-NEGOTIABLE) | refresh 回 202 + estimated_duration_seconds；status 欄位嚴格 = spec 列舉；無 spec 外 endpoint | T024, T025, T027 |
