# syntax=docker/dockerfile:1.7
#
# Dev container for ppo-smc-asset-allocation Python features (002, 001, 003, 004).
# Locked to python:3.11-slim to satisfy Constitution SC-007 (byte-identical Parquet
# across host OSes — Linux container is the single canonical environment).
#
# Build:  docker compose build dev
# Run:    docker compose run --rm dev bash

FROM python:3.11-slim-bookworm

# Build-time hardening & determinism
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONHASHSEED=0

# System packages: build toolchain for occasional pyarrow source builds; git for
# tooling that introspects the worktree (pytest, etc.).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ca-certificates \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Non-root user mirroring host uid=1000 to avoid root-owned files in mounted
# data/raw/. Override at build time with --build-arg HOST_UID=$(id -u) on Linux.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupadd --gid ${HOST_GID} dev \
 && useradd --uid ${HOST_UID} --gid ${HOST_GID} --create-home --shell /bin/bash dev

WORKDIR /workspace

# Copy dependency manifests first to maximise layer-cache hits. We also need the
# minimal package skeleton (src/) for `pip install -e .` to register the editable
# link; the bind mount at runtime overlays the same paths so editable resolves to
# the host source tree.
COPY --chown=dev:dev pyproject.toml requirements-lock.txt* ./
COPY --chown=dev:dev src/ ./src/

# Install runtime dependencies. When requirements-lock.txt is present (generated
# later by T004) we honour the locked set exactly via `pip-sync`. Until then we
# fall back to pyproject metadata so the very first Phase 1 build succeeds.
RUN if [ -f requirements-lock.txt ]; then \
        pip install -r requirements-lock.txt && pip install --no-deps -e . ; \
    else \
        echo "[Dockerfile] requirements-lock.txt missing — installing from pyproject (no exact pinning)" \
        && pip install -e ".[dev]" ; \
    fi

USER dev

# Default command opens an interactive shell. Override with `docker compose run`
# arguments for one-shot invocations (pytest, ppo-smc-data fetch, etc.).
CMD ["bash"]
