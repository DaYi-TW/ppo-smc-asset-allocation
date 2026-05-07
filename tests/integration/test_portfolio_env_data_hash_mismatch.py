"""Integration test：Parquet byte-flip → ``__init__`` raise（T014、FR-021、SC-006）。"""

from __future__ import annotations

import pytest

from portfolio_env import PortfolioEnv


def test_byte_flip_triggers_runtime_error(portfolio_default_config, tmp_portfolio_data_dir):
    """變更任一檔股票 Parquet 的單一 byte → ``PortfolioEnv(config)`` 立刻失敗。"""

    # 先確認乾淨快照可成功初始化（baseline）
    env = PortfolioEnv(portfolio_default_config)
    env.close()

    # 找到 NVDA Parquet 檔，flip 第 0 byte 後重寫（保留 metadata sidecar 不動）
    parquet_files = sorted(tmp_portfolio_data_dir.glob("nvda_daily_*.parquet"))
    assert parquet_files, "fixture 應產出 nvda_daily_*.parquet"
    target = parquet_files[0]
    raw = target.read_bytes()
    flipped = bytes([raw[0] ^ 0xFF]) + raw[1:]
    target.write_bytes(flipped)

    with pytest.raises(RuntimeError, match="hash mismatch"):
        PortfolioEnv(portfolio_default_config)


def test_missing_metadata_sidecar_raises(portfolio_default_config, tmp_portfolio_data_dir):
    """metadata sidecar 缺失 → 立即 raise（FR-021）。"""

    PortfolioEnv(portfolio_default_config).close()  # baseline

    meta_files = sorted(tmp_portfolio_data_dir.glob("amd_daily_*.parquet.meta.json"))
    assert meta_files, "fixture 應產出 amd metadata sidecar"
    meta_files[0].unlink()

    with pytest.raises(RuntimeError, match="metadata sidecar missing"):
        PortfolioEnv(portfolio_default_config)
