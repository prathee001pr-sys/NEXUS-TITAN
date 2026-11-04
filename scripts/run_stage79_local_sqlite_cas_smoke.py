"""Stage79 no-broker exact-head SQLite CAS smoke (entirely synthetic)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
    Stage55SyntheticBookBlocked,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="titan-stage79-") as folder:
        path = Path(folder) / "local_only.sqlite"
        a = Stage55IsolatedSyntheticExecutionBook(
            db_path=path, account_id="stage79-test-only", starting_cents=1_000_000,
            policy=Stage55SyntheticPolicy(),
        )
        b = Stage55IsolatedSyntheticExecutionBook(
            db_path=path, account_id="stage79-test-only", starting_cents=1_000_000,
            policy=Stage55SyntheticPolicy(),
        )
        old = a.inspect()
        b.reserve_synthetic_buy(
            request_id="other-writer", symbol="NIFTYOPT",
            quantity=1, limit_price_cents=1000, fee_buffer_cents=0,
        )
        stale_denied = False
        try:
            a.reserve_synthetic_buy(
                request_id="stale-writer", symbol="NIFTYOPT",
                quantity=1, limit_price_cents=1000, fee_buffer_cents=0,
                expected_revision=old.revision,
                expected_journal_tip=old.journal_tip,
            )
        except Stage55SyntheticBookBlocked:
            stale_denied = True
        status = a.inspect()
        packet = {
            "mode": "STAGE79_OPTIONAL_SINGLE_DB_CAS_RESEARCH",
            "sqlite_head_CAS_available": stale_denied,
            "same_file_integrity_verified": status.local_integrity_verified,
            "expected_single_committed_event": status.revision == 1,
            "global_mandatory_fo_risk_gateway": False,
            "legacy_direct_writes_blocked": False,
            "independent_market_and_risk_telemetry_verified": False,
            "single_global_capital_authority": False,
            "real_shadow_trading_started": False,
            "paper_order_authorized": False,
            "live_trading_enabled": False,
            "broker_orders_transmitted": 0,
            "verdict": "STAGE79_LOCAL_OPTIMISTIC_SQLITE_CAS_RESEARCH_NO_GO",
        }
    print(json.dumps(packet, sort_keys=True, indent=2))
    return 0 if (
        stale_denied and status.local_integrity_verified and status.revision == 1
        and not packet["live_trading_enabled"]
        and packet["broker_orders_transmitted"] == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
