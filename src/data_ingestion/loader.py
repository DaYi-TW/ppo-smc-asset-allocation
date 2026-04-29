"""快照載入器 — Phase 6（US4）公開 API 實作。

提供 `load_asset_snapshot` / `load_rate_snapshot` / `load_metadata` 三個函式，
從 `data/raw/` 中以 ticker 或 series_id 找到對應 Parquet + metadata sidecar，
驗證 schema 後回傳 pandas DataFrame 或 dataclass。

設計約束（spec FR-008、SC-003）：
- ticker case-insensitive：`load_asset_snapshot("nvda")` 與 `"NVDA"` 等價。
- 找不到檔案 → `FileNotFoundError`；找到多個（檔名衝突）→ `ValueError`。
- 載入後 dtype 必須符合 contracts/api.pyi 規定，否則 `ValueError`。
- 回傳 DataFrame 直接相容 001 spec 的 `batch_compute(df)` 輸入；無轉換層。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

# 延遲 import 避免 __init__.py 循環：dataclass 在 __init__.py 定義
__all__ = ["load_asset_snapshot", "load_rate_snapshot", "load_metadata"]


_ASSET_DTYPE_CONTRACT: dict[str, str] = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
    "quality_flag": "string",
}

_RATE_DTYPE_CONTRACT: dict[str, str] = {
    "rate_pct": "float64",
    "quality_flag": "string",
}


def _find_unique_parquet(prefix: str, data_dir: Path) -> Path:
    """在 data_dir 內尋找符合 `<prefix>_daily_*.parquet` 的單一檔案。"""
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data_dir does not exist: {data_dir}")

    pattern = f"{prefix}_daily_*.parquet"
    matches = sorted(data_dir.glob(pattern))
    # 排除 metadata sidecar 與 staging 暫存目錄產物
    matches = [m for m in matches if m.suffix == ".parquet" and not m.name.endswith(".meta.json")]

    if not matches:
        raise FileNotFoundError(
            f"no snapshot matching {pattern!r} in {data_dir}; "
            "run `ppo-smc-data fetch` first or check the prefix"
        )
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ValueError(
            f"multiple snapshots match {pattern!r} in {data_dir}: {names}; "
            "remove obsolete files so only one snapshot per asset remains"
        )
    return matches[0]


def _verify_dtypes(df: pd.DataFrame, contract: dict[str, str], parquet_path: Path) -> None:
    for col, expected in contract.items():
        if col not in df.columns:
            raise ValueError(
                f"snapshot {parquet_path.name} missing required column {col!r}"
            )
        actual = str(df[col].dtype)
        if actual != expected:
            raise ValueError(
                f"snapshot {parquet_path.name} column {col!r} has dtype {actual!r}, "
                f"contract requires {expected!r}"
            )


def _verify_index(df: pd.DataFrame, parquet_path: Path) -> None:
    if df.index.name != "date":
        raise ValueError(
            f"snapshot {parquet_path.name} index name is {df.index.name!r}, "
            "contract requires 'date'"
        )
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            f"snapshot {parquet_path.name} index is not DatetimeIndex"
        )
    if df.index.tz is not None:
        raise ValueError(
            f"snapshot {parquet_path.name} index is tz-aware ({df.index.tz}); "
            "contract requires UTC-naive datetime64[ns]"
        )


def load_asset_snapshot(
    ticker: str,
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    """載入單一資產 OHLCV Parquet 為 pandas DataFrame。"""
    if not ticker or not ticker.strip():
        raise ValueError("ticker must be a non-empty string")
    prefix = ticker.strip().lower()
    data_dir = Path(data_dir)

    parquet_path = _find_unique_parquet(prefix, data_dir)
    df = pd.read_parquet(parquet_path)
    _verify_dtypes(df, _ASSET_DTYPE_CONTRACT, parquet_path)
    _verify_index(df, parquet_path)
    return df


def load_rate_snapshot(
    series_id: str = "DTB3",
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    """載入 FRED rate Parquet 為 pandas DataFrame。"""
    if not series_id or not series_id.strip():
        raise ValueError("series_id must be a non-empty string")
    prefix = series_id.strip().lower()
    data_dir = Path(data_dir)

    parquet_path = _find_unique_parquet(prefix, data_dir)
    df = pd.read_parquet(parquet_path)
    _verify_dtypes(df, _RATE_DTYPE_CONTRACT, parquet_path)
    _verify_index(df, parquet_path)
    return df


def load_metadata(parquet_path: Path):
    """載入並驗證指定 Parquet 對應的 .meta.json sidecar，回傳 SnapshotMetadata。

    驗證流程（資料模型不變式 §3）：
    1. sidecar 必須存在（FileNotFoundError）
    2. 通過 contracts/snapshot-metadata.schema.json JSON Schema 驗證（ValueError）
    3. 解析為 frozen `SnapshotMetadata` dataclass 回傳
    """
    # 延遲 import：避免 import 時序問題（__init__.py → loader.py → __init__.py）
    import jsonschema

    from . import (
        ColumnSchema,
        IndexSchema,
        QualitySummary,
        SnapshotMetadata,
        TimeRange,
    )

    parquet_path = Path(parquet_path)
    meta_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")
    if not meta_path.is_file():
        raise FileNotFoundError(f"metadata sidecar not found: {meta_path}")

    payload = json.loads(meta_path.read_text(encoding="utf-8"))

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "specs"
        / "002-data-ingestion"
        / "contracts"
        / "snapshot-metadata.schema.json"
    )
    if schema_path.is_file():
        try:
            jsonschema.validate(payload, json.loads(schema_path.read_text(encoding="utf-8")))
        except jsonschema.ValidationError as exc:
            raise ValueError(
                f"metadata for {parquet_path.name} fails JSON Schema validation: {exc.message}"
            ) from exc

    try:
        return SnapshotMetadata(
            schema_version=payload["schema_version"],
            fetch_timestamp_utc=datetime.strptime(
                payload["fetch_timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ"
            ),
            data_source=payload["data_source"],
            data_source_call_params=dict(payload["data_source_call_params"]),
            upstream_package_versions=dict(payload["upstream_package_versions"]),
            sha256=payload["sha256"],
            row_count=payload["row_count"],
            column_schema=tuple(
                ColumnSchema(name=c["name"], dtype=c["dtype"])
                for c in payload["column_schema"]
            ),
            index_schema=IndexSchema(
                name=payload["index_schema"]["name"],
                dtype=payload["index_schema"]["dtype"],
                tz=payload["index_schema"]["tz"],
            ),
            time_range=TimeRange(
                start=payload["time_range"]["start"],
                end=payload["time_range"]["end"],
            ),
            quality_summary=QualitySummary(**payload["quality_summary"]),
            duplicate_dropped_timestamps=tuple(payload["duplicate_dropped_timestamps"]),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"metadata for {parquet_path.name} structure invalid: {exc}"
        ) from exc
