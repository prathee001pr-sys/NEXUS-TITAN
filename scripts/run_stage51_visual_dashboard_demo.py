"""Stage51: export a strictly synthetic Stage50 JSON for the offline visual demo.

Run from repository root:
    python scripts/run_stage51_visual_dashboard_demo.py
Then open src/nexus_titan/dashboard/static/stage51.html in a browser and use
"Choose JSON file" to select reports/stage51_paper_snapshot.json.

This creates an entirely NEW ephemeral, synthetic paper account. It does not
read or modify the user's existing account databases and has no broker/web
connections. The snapshot is not evidence of real account health.

The CLI never mints a signed approval or publishes secrets/order IDs.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.dashboard.paper_read_model import Stage50ReadOnlyPaperDashboard
from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import open_stage48_signed_paper_session


def generate_synthetic_snapshot() -> dict:
    with TemporaryDirectory(prefix="titan-stage51-visual-qa-") as location:
        root = Path(location)
        verifier = CryptographicApprovalVerifier(
            secret_key=secrets.token_urlsafe(32),
            db_path=root / "replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(
            PaperDeploymentConfig(
                account_id="STAGE51-DEMO-NOT-REAL",
                starting_capital=50000,
                virtual_state_dir=root / "virtual",
                research_db_path=root / "research.sqlite3",
                # Viewer-only demonstration: no new paper BUY intent!
                paper_orders_enabled=False,
            ), verifier=verifier,
        )
        fence = Stage49DurablePaperFence(session, db_path=root / "coordinator.sqlite3")
        snapshot = Stage50ReadOnlyPaperDashboard(fence).snapshot()
        # Only modify the *non-authoritative* display notes.
        snapshot["notes"].append(
            "STAGE51 DEMO FILE ONLY. Synthetic temporary account; NOT your actual data."
        )
        return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export standalone synthetic local dashboard demo")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "reports" / "stage51_paper_snapshot.json",
        help="A new JSON output path. Existing files are NEVER overwritten.",
    )
    args = parser.parse_args(argv)
    out = args.output
    try:
        if out.is_symlink() or out.exists():
            raise ValueError("Output file exists or is a symlink; no overwrites")
        if out.suffix.lower() != ".json":
            raise ValueError("Demo output must have a .json extension")
        content = generate_synthetic_snapshot()
        if content["safety"]["production_ready"] or content["safety"]["live_trading_enabled"]:
            raise ValueError("Invalid demo safety assertion")
        data = (json.dumps(content, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        if len(data) > 256 * 1024:
            raise ValueError("Snapshot exceeds the offline viewer's file limit")
        out.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(out, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            out.unlink(missing_ok=True)
            raise
    except (OSError, ValueError) as exc:
        print("STAGE51 DEMO EXPORT BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print("STAGE51_SYNTHETIC_DEMO_WRITTEN: " + str(out))
    print("This is NOT a real account snapshot or live-market dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
