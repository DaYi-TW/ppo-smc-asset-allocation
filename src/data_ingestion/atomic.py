"""Atomic publish helpers — staging dir + os.replace().

See research.md R5. Strategy: write all artefacts into a UTC-stamped staging
subdirectory under output_dir, then on full success move each file into
place via os.replace() (atomic on POSIX and on Windows when source/target
share the same volume — which they do, since staging is a child of the
output dir). On any exception during staging the directory is removed so
data/raw/ never sees partial output.

Windows note: os.replace fails with PermissionError if an antivirus / file
explorer holds a handle. We surface a friendlier message in that case so
researchers do not chase a generic OSError.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

_STAGING_PREFIX = ".staging-"


def make_staging_dir(output_dir: Path, *, now: datetime | None = None) -> Path:
    """Create and return ``output_dir/.staging-<UTC_TIMESTAMP>``.

    The output directory itself is created if missing. The staging dir is
    fresh — collisions raise FileExistsError so a stuck previous run is
    surfaced rather than silently overwritten.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    staging = output_dir / f"{_STAGING_PREFIX}{ts}"
    staging.mkdir(parents=False, exist_ok=False)
    return staging


def atomic_publish(staging: Path, output_dir: Path) -> tuple[Path, ...]:
    """Move every regular file inside ``staging`` to ``output_dir``.

    Returns the published paths in sorted order (deterministic for CI).
    Raises RuntimeError with a Windows-friendly hint if os.replace fails
    on a held file. Caller is responsible for cleaning up ``staging`` on
    error via ``staging_scope`` (recommended) or manually.
    """
    if not staging.is_dir():
        raise FileNotFoundError(f"staging dir does not exist: {staging}")

    published: list[Path] = []
    for src in sorted(staging.iterdir()):
        if not src.is_file():
            continue
        dst = output_dir / src.name
        try:
            os.replace(src, dst)
        except PermissionError as exc:
            if sys.platform == "win32":
                raise RuntimeError(
                    f"Failed to publish {src.name}: another process holds {dst}. "
                    "Close any program reading data/raw/ (e.g. Excel, Explorer "
                    "preview) and re-run."
                ) from exc
            raise
        published.append(dst)

    # Non-fatal: leftover non-file children (shouldn't exist) — leave for
    # operator inspection rather than silently removing recursively.
    with suppress(OSError):
        staging.rmdir()

    return tuple(published)


@contextmanager
def staging_scope(output_dir: Path, *, now: datetime | None = None) -> Iterator[Path]:
    """Context manager: create staging dir, clean up on exception.

    Successful exit leaves the staging dir in place (caller should have
    drained it via ``atomic_publish``). On exception the staging dir is
    removed recursively so partial files never appear under data/raw/.
    """
    staging = make_staging_dir(output_dir, now=now)
    try:
        yield staging
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
