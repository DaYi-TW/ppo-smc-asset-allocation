"""SMC overlay structure tests for episode artefact builder（feature 009 / T025-T027）。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_episode_artifact import build_episode_artifact

from inference_service.episode_schemas import SMCOverlay
from ppo_training.trajectory_writer import ASSET_NAMES_DEFAULT
from tests.unit.scripts.test_build_episode_artifact_basic import (  # noqa: F401  — 借用 mini_run fixture
    mini_run,
)


class TestSMCOverlayStructure:
    def test_overlay_has_six_assets(self, mini_run, tmp_path: Path) -> None:  # noqa: F811
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        overlay_map = payload["data"]["smcOverlayByAsset"]
        assert set(overlay_map.keys()) == set(ASSET_NAMES_DEFAULT)

    def test_each_overlay_validates(self, mini_run) -> None:  # noqa: F811
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        for _asset, overlay in payload["data"]["smcOverlayByAsset"].items():
            # SMCOverlay strict schema
            SMCOverlay.model_validate(overlay)

    def test_overlay_contains_lists(self, mini_run) -> None:  # noqa: F811
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        for _asset, overlay in payload["data"]["smcOverlayByAsset"].items():
            for key in ("swings", "zigzag", "fvgs", "obs", "breaks"):
                assert key in overlay
                assert isinstance(overlay[key], list)

    def test_break_kinds_are_valid(self, mini_run) -> None:  # noqa: F811
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        valid_kinds = {"BOS_BULL", "BOS_BEAR", "CHOCH_BULL", "CHOCH_BEAR"}
        for _asset, overlay in payload["data"]["smcOverlayByAsset"].items():
            for br in overlay["breaks"]:
                assert br["kind"] in valid_kinds

    def test_fvg_zone_uses_from_alias(self, mini_run) -> None:  # noqa: F811
        # contract: openapi 把 FVG 的開始時間命名為 `from`（避開 Python keyword 是
        # pydantic 內部事，序列化必須是 `from`）。
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        for _asset, overlay in payload["data"]["smcOverlayByAsset"].items():
            for fvg in overlay["fvgs"]:
                assert "from" in fvg
                assert "to" in fvg
                assert fvg["direction"] in {"bullish", "bearish"}
            for ob in overlay["obs"]:
                assert "from" in ob
                assert "to" in ob
                assert ob["direction"] in {"bullish", "bearish"}
