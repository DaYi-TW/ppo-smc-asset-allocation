"""ppo-smc-data CLI — fetch / verify / rebuild 子指令。

對應 contracts/cli.md。Phase 3 完成 fetch；verify / rebuild 留 NotImplementedError
帶 exit code 2，待 Phase 4 / 5。

退出代碼穩定性為對下游契約（contracts/cli.md §不變式 1），任何變更需 MAJOR bump。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import IngestionConfig, __version__
from .fetcher import fetch_all
from .sources.fred_source import FredApiKeyMissingError, FredFetchError
from .sources.yfinance_source import YfinanceFetchError

EXIT_OK = 0
EXIT_FETCH_OR_VERIFY_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_STRICT_UNEXPECTED_FILE = 3
EXIT_INTERRUPTED = 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ppo-smc-data",
        description="Data ingestion CLI for ppo-smc-asset-allocation feature 002.",
    )
    parser.add_argument(
        "--version", action="version", version=f"ppo-smc-data {__version__}"
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("data/raw"),
        help="Snapshot output directory (default: data/raw).",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )

    subparsers = parser.add_subparsers(dest="cmd")

    fetch = subparsers.add_parser("fetch", help="Fetch all 7 snapshots.")
    fetch.add_argument("--start", default="2018-01-01", help="ISO date, inclusive")
    fetch.add_argument("--end", default="2026-04-29", help="ISO date, inclusive")
    fetch.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config + env without making network calls.",
    )

    verify = subparsers.add_parser("verify", help="Verify snapshots against metadata.")
    verify.add_argument("--strict", action="store_true")

    rebuild = subparsers.add_parser("rebuild", help="Force re-fetch all snapshots.")
    rebuild.add_argument("--start", default=None)
    rebuild.add_argument("--end", default=None)
    rebuild.add_argument("--yes", action="store_true")

    return parser


def _cmd_fetch(args: argparse.Namespace) -> int:
    try:
        config = IngestionConfig(
            start_date=args.start,
            end_date=args.end,
            output_dir=Path(args.output_dir),
        )
    except ValueError as exc:
        sys.stderr.write(f"[fetch] ERROR: invalid configuration: {exc}\n")
        return EXIT_CONFIG_ERROR

    if args.dry_run:
        sys.stdout.write(
            f"[fetch] dry-run OK — would fetch {len(config.all_tickers())} tickers + "
            f"{config.fred_series_id} from {config.start_date} to {config.end_date}\n"
        )
        return EXIT_OK

    sys.stdout.write(
        f"[fetch] Starting ingestion: {config.start_date} → {config.end_date}\n"
    )

    def _progress(msg: str) -> None:
        sys.stdout.write(f"[fetch] {msg}\n")
        sys.stdout.flush()

    try:
        snapshots = fetch_all(config, progress=_progress)
    except FredApiKeyMissingError as exc:
        sys.stderr.write(f"[fetch] ERROR: {exc}\n")
        return EXIT_CONFIG_ERROR
    except (YfinanceFetchError, FredFetchError) as exc:
        sys.stderr.write(
            f"[fetch] ERROR: {exc}\n"
            f"        Staging directory has been cleaned up; "
            f"data/raw/ is unchanged.\n"
        )
        return EXIT_FETCH_OR_VERIFY_FAILED
    except KeyboardInterrupt:
        sys.stderr.write("[fetch] interrupted by user\n")
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover — last-resort
        sys.stderr.write(f"[fetch] ERROR: unexpected failure: {exc!r}\n")
        return EXIT_FETCH_OR_VERIFY_FAILED

    for snap in snapshots:
        sys.stdout.write(
            f"[fetch] {snap.parquet_path.name} ok "
            f"({snap.row_count} rows, sha256={snap.sha256[:7]}...)\n"
        )
    sys.stdout.write(
        f"[fetch] All {len(snapshots)} snapshots written to {config.output_dir}\n"
    )
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    sys.stderr.write("[verify] not implemented yet — lands in Phase 4 (T030-T036)\n")
    return EXIT_CONFIG_ERROR


def _cmd_rebuild(args: argparse.Namespace) -> int:
    sys.stderr.write("[rebuild] not implemented yet — lands in Phase 5 (T037-T040)\n")
    return EXIT_CONFIG_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return EXIT_OK

    try:
        if args.cmd == "fetch":
            return _cmd_fetch(args)
        if args.cmd == "verify":
            return _cmd_verify(args)
        if args.cmd == "rebuild":
            return _cmd_rebuild(args)
    except KeyboardInterrupt:
        sys.stderr.write(f"[{args.cmd}] interrupted by user\n")
        return EXIT_INTERRUPTED

    parser.print_help()
    return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
