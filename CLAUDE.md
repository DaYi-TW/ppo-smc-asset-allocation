# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository nature

This repo is **research and specification only — no source code exists yet**. It contains:

- `docs/` — the academic paper draft (Introduction, Related Work, Proposed Design), written in **Traditional Chinese**.
- `.specify/` — Spec Kit (SDD) v0.7.4 scaffolding: templates, workflows, hooks, and a constitution placeholder.
- `.claude/skills/` — installed `speckit-*` skills that drive the spec-driven development cycle.
- `README.md` — project overview with external links (Slides, YouTube demo, AI chat transcripts).

There is no `src/`, build system, test runner, package manifest, or language toolchain. Implementation will be created by running the Spec Kit workflow (`/speckit.specify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.implement`).

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
- **Feature**: 002-data-ingestion
- **Plan**: `specs/002-data-ingestion/plan.md`
- **Tasks**: `specs/002-data-ingestion/tasks.md` (57 tasks across 7 phases, 4 user stories; reviewed 2026-04-29)
- **Phase**: `/speckit.tasks` complete + auto-review pass. Next: `/speckit.implement`.
- **Sibling feature on hold**: 001-smc-feature-engine (62 tasks reviewed, ready for `/speckit.implement` after 002 produces `data/raw/` snapshots)
<!-- SPECKIT END -->

## Language and writing conventions

- All design docs and the README are in **Traditional Chinese**. Match this when editing or adding to `docs/` or `README.md`.
- Generated specs/plans/tasks under a future `specs/` directory should use the language the user prompts in.
- Citation markers like `[cite:157]` in `docs/introduction_revised.md` are intentional — preserve them.
