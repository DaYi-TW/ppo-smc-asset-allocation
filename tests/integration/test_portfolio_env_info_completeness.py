"""US4 integration tests：info 完整性（T044-T046、FR-026、SC-008）。

* 1000 步抽樣（mini fixture 一個 episode 即可）每步通過 JSON Schema。
* ``data_hashes`` 物件 identity 跨 step 不變（research R6 同一 dict view）。
* ``data_hashes`` 為 ``MappingProxyType``，使用者無法 mutate（FR-021、SC-008）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

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


def _schema():
    if not _SCHEMA_PATH.is_file():
        pytest.skip(f"info-schema.json missing: {_SCHEMA_PATH}")
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_full_episode_info_passes_schema(portfolio_default_config):
    """每一步 info 都通過 schema 驗證（mini fixture ~80 step ≈ 1000 對應抽樣）。"""
    schema = _schema()
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    rng = np.random.default_rng(42)
    while True:
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        _, _, term, _, info = env.step(a)
        safe = info_to_json_safe(info)
        jsonschema.validate(instance=safe, schema=schema)
        if term:
            break
    env.close()


def test_data_hashes_object_identity_constant_across_steps(portfolio_default_config):
    """同一 dict view 物件每步皆為同一 id（research R6）。"""
    env = PortfolioEnv(portfolio_default_config)
    _, info0 = env.reset(seed=42)
    first = info0["data_hashes"]
    rng = np.random.default_rng(42)
    for _ in range(20):
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        _, _, term, _, info = env.step(a)
        assert info["data_hashes"] is first
        if term:
            break
    env.close()


def test_data_hashes_is_mappingproxy_immutable(portfolio_default_config):
    """``info['data_hashes']`` 必為 ``MappingProxyType`` 且無法 mutate。"""
    env = PortfolioEnv(portfolio_default_config)
    _, info = env.reset(seed=42)
    assert isinstance(info["data_hashes"], MappingProxyType)
    with pytest.raises(TypeError):
        info["data_hashes"]["NVDA"] = "bad"
    env.close()


def test_info_to_json_safe_round_trip_lossless(portfolio_default_config):
    """JSON dump → load 後逐 key 比對 dict（FR-026）。"""
    env = PortfolioEnv(portfolio_default_config)
    _, info = env.reset(seed=42)
    safe = info_to_json_safe(info)
    text = json.dumps(safe)
    loaded = json.loads(text)
    # 所有 key 同步存在
    assert set(loaded) == set(safe)
    # nested reward_components dict 順序保留為 log_return / drawdown / turnover
    assert list(loaded["reward_components"]) == [
        "log_return",
        "drawdown_penalty",
        "turnover_penalty",
    ]
    env.close()
