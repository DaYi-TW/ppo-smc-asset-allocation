"""SHA-256 file hashing — chunked read for arbitrary file sizes.

See research.md R6: 64 KiB chunk size, lower-case hex digest, no streaming
short-cuts (we want the canonical hashlib output for cross-platform parity).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_BYTES = 64 * 1024


def sha256_of_file(path: Path) -> str:
    """Return lower-case hex SHA-256 digest of the file at ``path``."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
