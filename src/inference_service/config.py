"""ServiceConfig — 從 env var 載入並啟動時驗證一次（data-model §1）."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """啟動配置；缺欄位 / 路徑不存在 / cron 格式錯 → 啟動失敗."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    policy_path: Path
    data_root: Path = Path("data/raw")
    redis_url: str
    schedule_cron: str = "30 16 * * MON-FRI"
    schedule_timezone: str = "America/New_York"
    include_smc: bool = True
    seed: int = 42
    redis_channel: str = "predictions:latest"
    redis_key: str = "predictions:latest"
    redis_ttl_seconds: int = 604800
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    # 009 — Episode artefact path（image build 時 COPY 進來；缺檔則啟動失敗，FR-013）。
    episode_artefact_path: Path = Path("/app/artefact/episode_detail.json")
    # 010 — Live tracking dashboard（spec FR-001 / FR-002）。
    # live_artefact_dir：mutable artefact 目錄，host volume mount 進 container；
    # 啟動時若不存在自動建立（與 episode_artefact_path 不同：後者 image-baked 必存在）。
    live_artefact_dir: Path = Path("/app/runs/live_tracking")
    live_start_date: date = date(2026, 4, 29)  # OOS 結束 +1 NYSE 交易日
    live_initial_nav: float = 1.7291986  # OOS 終值，承接學術 baseline
    live_policy_run_id: str = ""  # 空字串 = 不啟用 Live tracking endpoint

    @field_validator("policy_path")
    @classmethod
    def _validate_policy_path(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"policy_path does not exist: {v}")
        if v.suffix != ".zip":
            raise ValueError(f"policy_path must end with .zip: {v}")
        return v

    @field_validator("data_root")
    @classmethod
    def _validate_data_root(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"data_root does not exist: {v}")
        parquet_files = list(v.glob("*.parquet"))
        if not parquet_files:
            raise ValueError(f"data_root has no *.parquet files: {v}")
        return v

    @field_validator("schedule_cron")
    @classmethod
    def _validate_schedule_cron(cls, v: str) -> str:
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(v)
        except ValueError as e:
            raise ValueError(f"invalid cron expression: {v} ({e})") from e
        return v
