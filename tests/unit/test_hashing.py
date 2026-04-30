"""hashing.sha256_of_file 對小/中/大三個檔案結果與 hashlib 標準路徑一致。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from data_ingestion.hashing import sha256_of_file


@pytest.mark.parametrize(
    "size_bytes",
    [
        1,           # 邊界：1 byte
        1024,        # < 64 KiB chunk
        64 * 1024,   # 剛好一個 chunk
        64 * 1024 + 7,  # 跨 chunk
        1024 * 1024,    # 1 MiB
    ],
)
def test_chunked_matches_full_read(tmp_path: Path, size_bytes: int) -> None:
    p = tmp_path / f"test-{size_bytes}.bin"
    payload = (b"x" * size_bytes)
    p.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert sha256_of_file(p) == expected


def test_returns_lowercase_hex(tmp_path: Path) -> None:
    p = tmp_path / "case.bin"
    p.write_bytes(b"hello")
    digest = sha256_of_file(p)
    assert digest == digest.lower()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    assert sha256_of_file(p) == hashlib.sha256(b"").hexdigest()
