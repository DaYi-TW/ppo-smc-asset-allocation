"""Stub entry point. Real argparse wiring lands in Phase 3 (T028, T029).

Until then `ppo-smc-data` and `ppo-smc-data --help` exit cleanly with a
"not implemented" notice so that the Phase 1 checkpoint can pass.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in ([], ["--help"], ["-h"]):
        sys.stdout.write(
            "ppo-smc-data 0.1.0 (stub)\n"
            "Subcommands fetch / verify / rebuild not implemented yet.\n"
            "See specs/002-data-ingestion/tasks.md for the implementation order.\n"
        )
        return 0
    if args == ["--version"]:
        sys.stdout.write("ppo-smc-data 0.1.0\n")
        return 0
    sys.stderr.write(f"ppo-smc-data: subcommand not implemented yet: {args!r}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
