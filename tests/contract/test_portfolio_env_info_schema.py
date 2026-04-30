"""Contract test：``info_to_json_safe(info)`` 對 ``contracts/info-schema.json``
驗證（T028、FR-026、SC-008）。"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import numpy as np
import pytest

from portfolio_env import PortfolioEnv, info_to_json_safe

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-ppo-training-env"
    / "contracts"
    / "info-schema.json"
)


def _load_schema() -> dict:
    if not _SCHEMA_PATH.is_file():
        pytest.skip(f"info-schema.json missing: {_SCHEMA_PATH}")
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_reset_info_passes_schema(portfolio_default_config):
    schema = _load_schema()
    env = PortfolioEnv(portfolio_default_config)
    _, info = env.reset(seed=42)
    safe = info_to_json_safe(info)
    jsonschema.validate(instance=safe, schema=schema)


def test_step_info_passes_schema(portfolio_default_config):
    schema = _load_schema()
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    rng = np.random.default_rng(42)
    for _ in range(10):
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        _, _, _, _, info = env.step(a)
        safe = info_to_json_safe(info)
        jsonschema.validate(instance=safe, schema=schema)


def test_missing_key_fails_schema(portfolio_default_config):
    schema = _load_schema()
    env = PortfolioEnv(portfolio_default_config)
    _, info = env.reset(seed=42)
    safe = info_to_json_safe(info)
    del safe["reward_components"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=safe, schema=schema)
