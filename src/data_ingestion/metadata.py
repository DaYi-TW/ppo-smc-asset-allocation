"""Metadata builder + JSON sidecar writer。

對應 research.md R10 與 contracts/snapshot-metadata.schema.json。每寫一份 metadata
都先在記憶體內以 jsonschema 自驗一次再落地，避免抓取一半才發現 schema 違規。

importlib.metadata 動態查詢套件版本字串（research R7）— metadata 紀錄的是抓取
當下的實際版本，不是 lock file 的宣告值。
"""

from __future__ import annotations

import importlib.metadata as md
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

import jsonschema
import pyarrow.parquet as pq

from . import (
    ColumnSchema,
    IndexSchema,
    QualitySummary,
    SnapshotMetadata,
    TimeRange,
)
from .hashing import sha256_of_file

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-data-ingestion"
    / "contracts"
    / "snapshot-metadata.schema.json"
)


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _package_version(name: str) -> str:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return "unknown"


def collect_upstream_versions(packages: Iterable[str]) -> dict[str, str]:
    """Resolve a stable, sorted dict of {package: version} for metadata."""
    return {name: _package_version(name) for name in sorted(packages)}


def utc_now_iso_z() -> str:
    """Current UTC time in ISO 8601 with explicit Z suffix (FR-014)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _column_schema_from_parquet(parquet_path: Path) -> tuple[ColumnSchema, ...]:
    """Read column dtypes back from the just-written parquet."""
    schema = pq.read_schema(parquet_path)
    pandas_to_contract = {
        "double": "float64",
        "float": "float64",
        "int64": "int64",
        "string": "string",
        "large_string": "string",
        "bool": "bool",
    }
    items: list[ColumnSchema] = []
    for field in schema:
        if field.name == "date":
            continue
        arrow_type = str(field.type)
        dtype = pandas_to_contract.get(arrow_type)
        if dtype is None:
            raise ValueError(
                f"unsupported arrow type {arrow_type!r} for column {field.name!r}; "
                "writer.py must be updated"
            )
        items.append(ColumnSchema(name=field.name, dtype=dtype))
    return tuple(items)


def build_metadata(
    *,
    parquet_path: Path,
    data_source: str,
    call_params: Mapping[str, object],
    time_range: tuple[str, str],
    quality_summary: Mapping[str, int],
    duplicate_dropped_timestamps: list[str],
    upstream_packages: Iterable[str] = ("yfinance", "fredapi", "pyarrow", "pandas"),
    fetch_timestamp_utc: str | None = None,
) -> SnapshotMetadata:
    """Construct a :class:`SnapshotMetadata` for the just-written ``parquet_path``."""
    parquet_path = Path(parquet_path)
    if not parquet_path.is_file():
        raise FileNotFoundError(f"parquet not found: {parquet_path}")

    sha = sha256_of_file(parquet_path)
    table_meta = pq.read_metadata(parquet_path)
    row_count = int(table_meta.num_rows)
    column_schema = _column_schema_from_parquet(parquet_path)

    # FR-014: timestamp must include explicit Z suffix.
    fetch_ts = fetch_timestamp_utc or utc_now_iso_z()
    fetch_dt = datetime.strptime(fetch_ts, "%Y-%m-%dT%H:%M:%SZ")

    return SnapshotMetadata(
        schema_version="1.0",
        fetch_timestamp_utc=fetch_dt,
        data_source=data_source,  # type: ignore[arg-type]
        data_source_call_params=dict(call_params),
        upstream_package_versions=collect_upstream_versions(upstream_packages),
        sha256=sha,
        row_count=row_count,
        column_schema=column_schema,
        index_schema=IndexSchema(name="date", dtype="datetime64[ns]", tz=None),
        time_range=TimeRange(start=time_range[0], end=time_range[1]),
        quality_summary=QualitySummary(**dict(quality_summary)),
        duplicate_dropped_timestamps=tuple(duplicate_dropped_timestamps),
    )


def metadata_to_dict(meta: SnapshotMetadata) -> dict:
    """Serialise a SnapshotMetadata to a JSON-Schema-compliant dict."""
    return {
        "schema_version": meta.schema_version,
        "fetch_timestamp_utc": meta.fetch_timestamp_utc.replace(
            tzinfo=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": meta.data_source,
        "data_source_call_params": dict(meta.data_source_call_params),
        "upstream_package_versions": dict(meta.upstream_package_versions),
        "sha256": meta.sha256,
        "row_count": meta.row_count,
        "column_schema": [
            {"name": c.name, "dtype": c.dtype} for c in meta.column_schema
        ],
        "index_schema": {
            "name": meta.index_schema.name,
            "dtype": meta.index_schema.dtype,
            "tz": meta.index_schema.tz,
        },
        "time_range": {"start": meta.time_range.start, "end": meta.time_range.end},
        "quality_summary": {
            "ok": meta.quality_summary.ok,
            "missing_close": meta.quality_summary.missing_close,
            "zero_volume": meta.quality_summary.zero_volume,
            "missing_rate": meta.quality_summary.missing_rate,
            "duplicate_dropped": meta.quality_summary.duplicate_dropped,
        },
        "duplicate_dropped_timestamps": list(meta.duplicate_dropped_timestamps),
    }


def write_metadata_json(meta: SnapshotMetadata, parquet_path: Path) -> Path:
    """Validate then write ``<parquet_path>.meta.json`` next to the parquet.

    Returns the metadata file path. Raises ``ValueError`` if the produced
    payload fails the JSON Schema (catches builder bugs before they reach
    disk).
    """
    parquet_path = Path(parquet_path)
    payload = metadata_to_dict(meta)
    try:
        jsonschema.validate(payload, _load_schema())
    except jsonschema.ValidationError as exc:
        raise ValueError(
            f"metadata builder produced a payload that fails schema validation: "
            f"{exc.message} (path: {list(exc.absolute_path)})"
        ) from exc

    meta_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False),
        encoding="utf-8",
    )
    return meta_path
