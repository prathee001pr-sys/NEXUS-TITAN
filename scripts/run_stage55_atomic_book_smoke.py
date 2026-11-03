"""Stage55 no-broker demonstration of atomic synthetic reserve/fill/cancel.

The values represent fictional local equity-delivery fills, not real trades.
Only the disposable Stage55 SQLite exists here. Does not touch Stage43,
research ledger, Stage49 coordinator, Stage53 holds or external providers.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage55-isolated-") as dirname:
        db = Path(dirname) / "one-domain-synthetic.sqlite3"
        book = Stage55IsolatedSyntheticExecutionBook(
            db_path=db, account_id="STAGE55-SYNTHETIC", starting_cents=5_000_000,
        )
        opened = book.reserve_synthetic_buy(
            request_id="DEMO-OPEN", symbol="QA-ABC",
            quantity=10, limit_price_cents=10_000, fee_buffer_cents=1000,
        )
        before = asdict(book.inspect())
        partial = book.record_simulated_fill(
            order_id="DEMO-OPEN", fill_id="DEMO-FILL-ONE",
            quantity=3, price_cents=9_000, fee_cents=100,
            evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        )
        after_partial = asdict(book.inspect())
        cancel = book.cancel_unfilled(
            order_id="DEMO-OPEN", cancel_id="DEMO-CANCEL",
            evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        )
        after_cancel = asdict(book.inspect())
        opened_again = Stage55IsolatedSyntheticExecutionBook(
            db_path=db, account_id="STAGE55-SYNTHETIC", starting_cents=5_000_000,
        )
        restart_matches = asdict(opened_again.inspect()) == after_cancel
        evidence = {
            "mode": "STAGE55_ISOLATED_SYNTHETIC_SINGLE_DB_ONLY",
            "initial_cents": 5_000_000,
            "opened_order_state": opened.order_state,
            "partial_order_state": partial.order_state,
            "cancel_order_state": cancel.order_state,
            "before": before,
            "after_partial": after_partial,
            "after_cancel": after_cancel,
            "restart_consistency_verified": restart_matches,
        }
        print(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False))
        return 0 if all((
            opened.order_state == "PENDING_SYNTHETIC",
            partial.order_state == "PARTIAL_SYNTHETIC",
            cancel.order_state == "CANCELLED_SYNTHETIC",
            before["open_reserved_cents"] == 101000,
            after_partial["paid_notional_cents"] == 27000,
            after_cancel["open_reserved_cents"] == 0,
            after_cancel["cash_cents"] == 4_972_900,
            restart_matches, not after_cancel["production_ready"],
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
