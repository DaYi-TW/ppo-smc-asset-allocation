"""Byte-identical contract test for episode artefact builder（feature 009 / T028-T029）。

對齊 spec FR-014（Constitution Principle I）。同一份 trajectory + OHLC + summary
連跑兩次 ``build_episode_artifact``，必須產出 sha256 完全相同的 JSON bytes。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.build_episode_artifact import build_episode_artifact

from tests.unit.scripts.test_build_episode_artifact_basic import (  # noqa: F401  — 共用 mini_run fixture
    mini_run,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestArtifactByteIdentical:
    def test_two_runs_produce_identical_sha256(self, mini_run, tmp_path: Path) -> None:  # noqa: F811
        out_a = tmp_path / "run_a.json"
        out_b = tmp_path / "run_b.json"

        build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=out_a,
        )
        build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=out_b,
        )

        assert _sha256(out_a) == _sha256(out_b), "byte-identical broken"

    def test_json_uses_canonical_serialization(self, mini_run, tmp_path: Path) -> None:  # noqa: F811
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=tmp_path / "out.json",
        )
        text = out.read_text(encoding="utf-8")
        # canonical: separators=(",", ":") → 不帶空白
        assert ", " not in text
        assert ": " not in text
        # 必為單行（無 indent）
        assert "\n" not in text.rstrip("\n")
