"""T008 — ServiceConfig env-var loading + 啟動驗證 (RED → GREEN at T013)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


def test_config_loads_from_env(monkeypatch: pytest.MonkeyPatch, policy_path: Path, data_root: Path) -> None:
    """正常路徑：env var 全部就位 → ServiceConfig() 載入成功。"""
    from inference_service.config import ServiceConfig

    monkeypatch.setenv("POLICY_PATH", str(policy_path))
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    cfg = ServiceConfig()

    assert cfg.policy_path == policy_path
    assert cfg.data_root == data_root
    assert cfg.redis_url == "redis://localhost:6379/0"
    # Defaults preserved
    assert cfg.schedule_cron == "30 16 * * MON-FRI"
    assert cfg.schedule_timezone == "America/New_York"
    assert cfg.include_smc is True
    assert cfg.seed == 42
    assert cfg.redis_channel == "predictions:latest"
    assert cfg.redis_key == "predictions:latest"
    assert cfg.redis_ttl_seconds == 604800
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8000


def test_config_missing_policy_raises(monkeypatch: pytest.MonkeyPatch, data_root: Path, tmp_path: Path) -> None:
    """policy_path 指向不存在檔 → ValidationError."""
    from inference_service.config import ServiceConfig

    monkeypatch.setenv("POLICY_PATH", str(tmp_path / "nonexistent.zip"))
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError, match="policy_path"):
        ServiceConfig()


def test_config_policy_must_be_zip(monkeypatch: pytest.MonkeyPatch, data_root: Path, tmp_path: Path) -> None:
    """policy_path 不是 .zip → ValidationError."""
    from inference_service.config import ServiceConfig

    fake = tmp_path / "policy.txt"
    fake.write_text("not a zip")
    monkeypatch.setenv("POLICY_PATH", str(fake))
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError, match=r"\.zip"):
        ServiceConfig()


def test_config_data_root_must_have_parquet(monkeypatch: pytest.MonkeyPatch, policy_path: Path, tmp_path: Path) -> None:
    """data_root 沒 .parquet → ValidationError."""
    from inference_service.config import ServiceConfig

    empty = tmp_path / "empty_data"
    empty.mkdir()
    monkeypatch.setenv("POLICY_PATH", str(policy_path))
    monkeypatch.setenv("DATA_ROOT", str(empty))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError, match="parquet"):
        ServiceConfig()


def test_config_invalid_cron_raises(monkeypatch: pytest.MonkeyPatch, policy_path: Path, data_root: Path) -> None:
    """SCHEDULE_CRON 格式不對 → ValidationError（pre-validate via APScheduler）."""
    from inference_service.config import ServiceConfig

    monkeypatch.setenv("POLICY_PATH", str(policy_path))
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SCHEDULE_CRON", "this is not cron")

    with pytest.raises(ValidationError, match="cron"):
        ServiceConfig()
