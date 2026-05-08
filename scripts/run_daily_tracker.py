"""T023 — Daily tracker CLI wrapper.

對應 spec 010 FR-002 / FR-026 / SC-001。

使用方式::

    python scripts/run_daily_tracker.py \
        --policy-run-id ppo_smc_v1 \
        --artefact-dir runs/ppo_smc_v1/live_tracking \
        --status-path  runs/ppo_smc_v1/live_tracking/live_tracking_status.json

退出碼：
* ``0`` — pipeline 成功 (final_status in {"succeeded", "noop"})
* ``1`` — pipeline 失敗（DATA_FETCH / INFERENCE / WRITE 任一）

Note：本 CLI 是「手動觸發」的入口（spec 明確排除 GitHub Actions cron）；
``FrameBuilder`` 由 ``--frame-builder-module:func`` 動態 import 注入，未提供
時 pipeline 會把 status 標記為 ``INFERENCE: frame_builder not configured`` 並
exit 1（保護機制 — 真實 fetch+inference 接線在 T014/T018 階段陸續落地）。
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from live_tracking.pipeline import (
    DailyTrackerPipeline,
    FrameBuilder,
    PipelineResult,
)
from live_tracking.status import LiveTrackingStatus
from live_tracking.store import LiveTrackingStore

logger = logging.getLogger("run_daily_tracker")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one daily tracker pipeline iteration.",
    )
    parser.add_argument(
        "--policy-run-id",
        required=True,
        help="Policy run id to associate with this live tracking artefact.",
    )
    parser.add_argument(
        "--artefact-dir",
        type=Path,
        required=True,
        help="Directory containing live_tracking.json (created if absent).",
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=None,
        help="Path to live_tracking_status.json (default: <artefact-dir>/live_tracking_status.json).",
    )
    parser.add_argument(
        "--initial-nav",
        type=float,
        default=1.7291986,
        help="Starting NAV for the live tracking series (default: OOS terminal NAV).",
    )
    parser.add_argument(
        "--start-anchor",
        type=date.fromisoformat,
        default=date(2026, 4, 29),
        help="Calendar date of the first live frame in YYYY-MM-DD form.",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="Override today (UTC) — useful for fixture/replay runs.",
    )
    parser.add_argument(
        "--frame-builder",
        type=str,
        default=None,
        help="Dotted path 'module:callable' returning the FrameBuilder. "
        "Omit to fail-fast with status.last_error set.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args(argv)


def _load_frame_builder(spec: str | None) -> FrameBuilder | None:
    if spec is None:
        return None
    if ":" not in spec:
        raise SystemExit(
            f"--frame-builder must be 'module:callable' (got '{spec}')"
        )
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    builder = getattr(module, attr, None)
    if builder is None or not callable(builder):
        raise SystemExit(f"frame builder '{spec}' is not callable")
    return builder  # type: ignore[return-value]


def _run(args: argparse.Namespace) -> PipelineResult | None:
    artefact_dir: Path = args.artefact_dir
    artefact_dir.mkdir(parents=True, exist_ok=True)
    artefact_path = artefact_dir / "live_tracking.json"
    status_path: Path = args.status_path or (artefact_dir / "live_tracking_status.json")

    # Recover orphan lock (research §R6) — CLI starts a fresh process, so any
    # is_running=True from a previous crash is by definition stale.
    if status_path.exists():
        status = LiveTrackingStatus.load(status_path)
        if status.is_running:
            status.is_running = False
            status.running_pid = None
            status.running_started_at = None
            status.write(status_path)
            logger.warning(
                "recovered_orphan_lock status_path=%s previous_pid=%s",
                status_path,
                status.running_pid,
            )

    builder = _load_frame_builder(args.frame_builder)

    pipeline = DailyTrackerPipeline(
        store=LiveTrackingStore(artefact_path),
        status_path=status_path,
        build_frames=builder if builder is not None else _unconfigured_builder,
        initial_nav=args.initial_nav,
        start_anchor=args.start_anchor,
        policy_run_id=args.policy_run_id,
    )
    today = args.today or datetime.now(UTC).date()
    pipeline_id = str(uuid.uuid4())
    return pipeline.run_once(today, pipeline_id=pipeline_id)


def _unconfigured_builder(**_kwargs: object) -> object:
    """Sentinel builder — raises so pipeline marks status 'INFERENCE: ...'.

    當 ``--frame-builder`` 沒提供時走這條，留給後續 task 把真實 fetch/inference
    pipeline 接上後再以 dotted path 注入。
    """
    raise RuntimeError(
        "frame_builder not configured — pass --frame-builder module:callable"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = _run(args)
    except Exception as exc:
        logger.exception("daily_tracker_cli_failed error=%s", exc)
        return 1
    if result is None:
        return 1
    if result.final_status in {"succeeded", "noop"}:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
