"""Stage68 read-only selected combined candidate offline gate (NO-GO)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage68_combined_candidate import (
    Stage68CandidateBlocked, inspect_stage68_combined_candidate,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage68 selected integration candidate no-go")
    p.add_argument("--repo-root", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        audit = inspect_stage68_combined_candidate(args.repo_root)
        print(json.dumps(asdict(audit), indent=2, sort_keys=True, allow_nan=False))
        return 0 if audit.candidate_local_checks_passed else 2
    except (ValueError, OSError, TypeError, Stage68CandidateBlocked) as exc:
        print(json.dumps({
            "scope": "STAGE68_SELECTED_OFFLINE_INTEGRATION_CANDIDATE_NO_GO",
            "candidate_local_checks_passed": False,
            "safe_to_merge": False,
            "production_ready": False,
            "real_money_trading_enabled": False,
            "broker_orders_transmitted": 0,
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
