"""快照驗證 — Phase 4（US2）公開 API 實作。

提供 `verify_snapshot(parquet_path)` 與 `verify_all(data_dir)`，純本地比對：
  1. 重算 SHA-256 與 metadata 中的 ``sha256`` 一致；
  2. Parquet 實際 row_count 與 metadata 一致；
  3. Parquet 實際欄位 schema 與 metadata.column_schema 一致；
  4. metadata sidecar 通過 JSON Schema 驗證（由 ``load_metadata`` 完成）。

不做網路呼叫、不需 ``FRED_API_KEY``。CI 應能離線執行。
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from .hashing import sha256_of_file

__all__ = ["verify_all", "verify_snapshot"]


# pyarrow type → contract dtype 映射，與 metadata builder 同步
_ARROW_TYPE_TO_DTYPE = {
    "double": "float64",
    "float": "float64",
    "int64": "int64",
    "int32": "int64",
    "string": "string",
    "large_string": "string",
    "bool": "bool",
}


def _arrow_field_dtype(field) -> str | None:
    """把 pyarrow Field 對應到 contract dtype；無法對應回傳 None。"""
    type_str = str(field.type)
    if type_str in _ARROW_TYPE_TO_DTYPE:
        return _ARROW_TYPE_TO_DTYPE[type_str]
    if type_str.startswith("timestamp"):
        return None  # index 欄位、不在 column_schema
    return None


def _make_result(
    parquet_path: Path,
    metadata_path: Path,
    sha256_match: bool,
    row_count_match: bool,
    schema_match: bool,
    expected_sha256: str,
    actual_sha256: str,
    message: str,
):
    """延遲 import VerifyResult 以避免 __init__.py 循環。"""
    from . import VerifyResult

    return VerifyResult(
        parquet_path=parquet_path,
        metadata_path=metadata_path,
        sha256_match=sha256_match,
        row_count_match=row_count_match,
        schema_match=schema_match,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        message=message,
    )


def verify_snapshot(parquet_path: Path):
    """Verify a single Parquet against its metadata sidecar.

    若 metadata 缺失 / schema 不合規 / Parquet 不存在 → 回傳 ``VerifyResult``
    的 ``ok`` 為 False，``message`` 含具體原因。本函式不拋例外（除非真的無法
    建立 result，例如連 path 都讀不出來）— 例外語意留給 caller 經由 .ok 判斷。
    """
    from . import load_metadata  # 延遲 import 避免循環

    parquet_path = Path(parquet_path)
    metadata_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")

    # 1. Parquet 不存在 → 立即失敗
    if not parquet_path.is_file():
        return _make_result(
            parquet_path=parquet_path,
            metadata_path=metadata_path,
            sha256_match=False,
            row_count_match=False,
            schema_match=False,
            expected_sha256="",
            actual_sha256="",
            message=f"MISSING: parquet file not found: {parquet_path.name}",
        )

    # 2. metadata sidecar 不存在或 schema 不合規 → load_metadata 會拋
    try:
        meta = load_metadata(parquet_path)
    except FileNotFoundError:
        return _make_result(
            parquet_path=parquet_path,
            metadata_path=metadata_path,
            sha256_match=False,
            row_count_match=False,
            schema_match=False,
            expected_sha256="",
            actual_sha256="",
            message=f"MISSING: metadata sidecar not found: {metadata_path.name}",
        )
    except ValueError as exc:
        return _make_result(
            parquet_path=parquet_path,
            metadata_path=metadata_path,
            sha256_match=False,
            row_count_match=False,
            schema_match=False,
            expected_sha256="",
            actual_sha256="",
            message=f"FAIL: metadata schema invalid: {exc}",
        )

    # 3. SHA-256
    actual_sha = sha256_of_file(parquet_path)
    sha_ok = actual_sha == meta.sha256

    # 4. row_count + schema（讀取 Parquet 結構，不做完整載入）
    # 若 Parquet 已被竄改到 footer 損壞，pq.read_metadata 會拋 ArrowInvalid。
    # 此時 sha_ok 必為 False，已給出明確失敗原因；row_count / schema 標記為
    # 不符即可，不必再重複 raise。
    rows_ok = False
    schema_ok = False
    schema_problems: list[str] = []
    actual_rows = -1
    try:
        pq_meta = pq.read_metadata(parquet_path)
        actual_rows = pq_meta.num_rows
        rows_ok = actual_rows == meta.row_count

        pq_schema = pq.read_schema(parquet_path)
        pq_fields = {f.name: f for f in pq_schema}
        for col in meta.column_schema:
            field = pq_fields.get(col.name)
            if field is None:
                schema_problems.append(f"missing column {col.name!r}")
                continue
            actual_dtype = _arrow_field_dtype(field)
            if actual_dtype != col.dtype:
                schema_problems.append(
                    f"column {col.name!r} dtype {actual_dtype!r} != {col.dtype!r}"
                )
        schema_ok = not schema_problems
    except Exception as exc:
        # Parquet 結構讀取失敗 — 通常是檔案損壞，sha256 應已抓到
        schema_problems.append(f"parquet structure unreadable: {exc}")

    # 組合人類可讀訊息（first failure reason）
    if sha_ok and rows_ok and schema_ok:
        message = "OK"
    else:
        if not sha_ok:
            message = f"FAIL: sha256 mismatch (expected {meta.sha256[:16]}…, actual {actual_sha[:16]}…)"
        elif not rows_ok:
            message = f"FAIL: row_count mismatch (expected {meta.row_count}, actual {actual_rows})"
        else:
            message = "FAIL: schema mismatch — " + "; ".join(schema_problems)

    return _make_result(
        parquet_path=parquet_path,
        metadata_path=metadata_path,
        sha256_match=sha_ok,
        row_count_match=rows_ok,
        schema_match=schema_ok,
        expected_sha256=meta.sha256,
        actual_sha256=actual_sha,
        message=message,
    )


def verify_all(data_dir: Path = Path("data/raw")):
    """Verify every snapshot in ``data_dir``.

    回傳依檔名排序的 ``tuple[VerifyResult, ...]``，CI stdout 順序穩定。
    若 ``data_dir`` 不存在 → 拋 ``FileNotFoundError``（caller 應對應 exit 2）。
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data_dir does not exist: {data_dir}")

    parquet_files = sorted(
        p for p in data_dir.glob("*.parquet") if not p.name.endswith(".meta.json")
    )
    return tuple(verify_snapshot(p) for p in parquet_files)
