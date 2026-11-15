"""Stage52 no-write security evidence report, never a release approval.

Usage:
    python scripts/run_stage52_security_audit.py
    python scripts/run_stage52_security_audit.py --root /path/to/candidate-tree

This inspects bounded local files; a passing static scan only means that
a known code/UI shape is present. The output always blocks live trading.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.release_security_audit import inspect_stage52_security_sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Stage52 local security scan, always fail-closed for production",
    )
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Exact checked-out local candidate source tree")
    args = parser.parse_args(argv)
    report = inspect_stage52_security_sources(args.root)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    # Success here means source inspection ran and known patterns were
    # confirmed. It does NOT mean production-ready or global enforcement.
    return 0 if report.local_structural_controls_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
