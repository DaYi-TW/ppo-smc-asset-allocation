# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository nature

The repo is a hybrid: academic paper drafts under `docs/`, Spec Kit (SDD) scaffolding under `.specify/`, and an in-progress Python implementation. Top-level layout:

- `docs/` — academic paper draft (Introduction, Related Work, Proposed Design), Traditional Chinese.
- `.specify/` — Spec Kit (SDD) v0.7.4 scaffolding (templates, workflows, hooks, constitution).
- `.claude/skills/` — installed `speckit-*` skills that drive the spec-driven development cycle.
- `src/data_ingestion/` — feature 002 implementation (Python 3.11, pyarrow/pandas; CLI `ppo-smc-data fetch|verify|rebuild`).
- `tests/{unit,integration,contract}/` — pytest suite for feature 002 (131 tests, ~91% coverage).
- `tests/fixtures/golden_snapshots/` — committed reference Parquet for SC-007 cross-platform byte-identical proof.
- `data/raw/` — destination for committed Parquet snapshots (populated by T055).
- `Dockerfile` + `docker-compose.yml` — canonical dev container (pinned pandas/pyarrow patch versions for byte-identical Parquet).
- `requirements-lock.txt` — pip-compile lock for SC-007 reproducibility.
- `README.md` — project overview + links (Slides, YouTube demo, AI chat transcripts).

The dev container is the canonical environment — run everything via `docker compose run --rm dev <cmd>` (e.g. `pytest tests/`, `ppo-smc-data verify`).

## Project: PPO + SMC Multi-Asset Allocation

The planned system combines two ideas not previously integrated in the literature:

1. **PPO (Proximal Policy Optimization)** as the RL agent for continuous portfolio weight allocation across three buckets:
   - **Risk-On**: AI/semiconductor equities (NVDA, AMD, TSM)
   - **Risk-Off**: Gold (GLD) and long-duration treasuries (TLT)
   - **Cash**: absolute safety bucket for liquidity crises
2. **SMC (Smart Money Concepts)** features quantified into the RL **observation space** — this is the core novelty. Specifically:
   - BOS / CHoCh as discrete `[0, 1, -1]` market-structure signals
   - FVG (Fair Value Gap) as price-distance percentage
   - OB (Order Block) as touch state + distance ratio

The reward function explicitly penalizes max drawdown (MDD) and slippage/transaction cost, not just return. This is load-bearing — when designing the agent, do not reduce reward to pure PnL.

The planned deployment architecture is a **microservices "War Room"**: Python (Gymnasium/PPO inference) ↔ Spring Boot API gateway with Kafka ↔ React dashboard. Keep this three-tier split in mind when generating plans.

See `docs/proposed_design.md` for the authoritative spec; `docs/related_work.md` explains why each design choice exists relative to prior work.

## Spec Kit workflow

This repo is configured for `integration: claude` and `script: ps` (PowerShell). The full SDD cycle is `specify → plan → tasks → implement` with manual review gates between specify and plan, and between plan and tasks (see `.specify/workflows/speckit/workflow.yml`).

Auto-commit hooks are enabled around every speckit phase (`before_*` and `after_*` in `.specify/extensions.yml`). When invoking a `/speckit.*` skill, expect git commit prompts before and after — these are not bugs.

The project constitution at `.specify/memory/constitution.md` is **ratified at v1.1.0** (2026-04-29). It defines five core principles — three are NON-NEGOTIABLE: **Reproducibility (I)**, **Risk-First Reward (III)**, and **Spec-First (V)**. When running `/speckit.plan`, expand these five principles into the empty Constitution Check block in `plan-template.md` (lines 30-34) as concrete gate items for that feature's `plan.md`.

Helper PowerShell scripts live in `.specify/scripts/powershell/` (`create-new-feature.ps1`, `setup-plan.ps1`, `check-prerequisites.ps1`, `common.ps1`) — these are invoked by the speckit skills, not directly by the user.

## Active Spec Kit feature

<!-- SPECKIT START -->
- **Feature**: 010-live-tracking-dashboard
- **Spec**: `specs/010-live-tracking-dashboard/spec.md`
- **Plan**: `specs/010-live-tracking-dashboard/plan.md`
- **Phase**: plan 完成（2026-05-08）— spec 27 FR + 9 SC 對齊 checklist 16/16 ✓；plan.md Constitution Gates 五原則展開為具體 gate items（Principle I OOS byte-identical vs Live append-only 區隔；Principle III reward parity test；Principle V endpoint 鎖死 spec）；research.md 12 decisions（atomic write / NYSE calendar / single-step env / SMC full recompute / orphan lock recovery / 三類 error 前綴）；data-model.md 5 entities（LiveTrackingArtefact / LiveTrackingStatus / DailyTrackerPipelineRun / RefreshAcceptedResponse / EpisodeListItem）；contracts/openapi-live-tracking.yaml 兩 endpoint 完整定義；quickstart.md e2e 走法。Next: `/speckit.tasks` 拆 phases 0~7。
- **Scope**: 把 007 Overview 從「OOS 回測展示」轉為「每日 prediction tracking dashboard」。新增 mutable `runs/<policy_run_id>/live_tracking/live_tracking.json`（schema = 009 EpisodeDetail）、`scripts/run_daily_tracker.py`（fetch → inference → single-step env → append → SMC overlay 全段重算 → atomic write）、005 兩個新 endpoint（`POST /api/v1/episodes/live/refresh` + `GET /api/v1/episodes/live/status`）、006 對應 proxy、007 OverviewPage 預設 Live + 手動更新按鈕 + lag badge。**不**重訓 PPO、**不**動 env / reward.py / observation shape / 008 SMC 內部 / 009 build_episode_artifact.py。**不**做 GitHub Actions cron（spec OUT OF SCOPE）。
- **Sibling features**:
  - 009-episode-detail-store: 已 implement 完成；010 重用 EpisodeDetail Pydantic schema（OOS / Live 共用同一 DTO 是 SC-007 硬約束）。
  - 008-smc-engine-v2: 010 daily pipeline 重用 `batch_compute_events` 全段重算 SMC overlay。
  - 007-react-warroom: OverviewPage 預設改 Live、加 header 控件（按鈕 + badge + 失敗 toast）。
  - 005-inference-service: 010 在其上加 2 個 endpoint 並把 `EpisodeStore` 重構為 `MultiSourceEpisodeStore`（OOS + Live 雙源）。
  - 006-spring-gateway: 010 加兩個 proxy endpoint + contract test，OpenAPI 對齊。
  - 003-ppo-training-env / 004-ppo-trainer: black box import；reward function 沿用 (return − drawdown_penalty − cost_penalty)，由 Constitution Principle III gate test 強制 parity。
<!-- SPECKIT END -->

## Language and writing conventions

- All design docs and the README are in **Traditional Chinese**. Match this when editing or adding to `docs/` or `README.md`.
- Generated specs/plans/tasks under a future `specs/` directory should use the language the user prompts in.
- Citation markers like `[cite:157]` in `docs/introduction_revised.md` are intentional — preserve them.
