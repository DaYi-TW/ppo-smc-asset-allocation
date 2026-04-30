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
- **Feature**: 003-ppo-training-env
- **Spec**: `specs/003-ppo-training-env/spec.md`
- **Phase**: `/speckit.specify` complete (validation checklist passed). Next: human review gate → `/speckit.plan`.
- **Sibling features**:
  - 002-data-ingestion: Phases 1–7 implemented (T000–T053, T048+T049, T052a). 131 tests pass, coverage 90.98%, mypy/ruff clean. Remaining: T054 (manual quickstart walkthrough), T055 (real fetch with `FRED_API_KEY` → commit `data/raw/`), T056 (PR review gate).
  - 001-smc-feature-engine: 62 tasks ready, unblocks once T055 lands `data/raw/`.
<!-- SPECKIT END -->

## Language and writing conventions

- All design docs and the README are in **Traditional Chinese**. Match this when editing or adding to `docs/` or `README.md`.
- Generated specs/plans/tasks under a future `specs/` directory should use the language the user prompts in.
- Citation markers like `[cite:157]` in `docs/introduction_revised.md` are intentional — preserve them.
