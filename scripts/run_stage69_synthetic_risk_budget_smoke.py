"""Stage69 disposable standalone brokerless risk-budget smoke — NO TRADES."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.brokerless_risk_veto import (
    Stage56SyntheticIntent, Stage56SyntheticQuote,
)
from nexus_titan.operations.stage69_risk_budget_preflight import (
    Stage69UntrustedRiskTelemetry, inspect_stage69_synthetic_risk_budget,
)
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53SyntheticCapitalAuthority,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage69-synthetic-") as folder:
        authority = Stage53SyntheticCapitalAuthority(
            db_path=Path(folder) / "disposable-budget.sqlite3",
            account_id="QA69",
            starting_cents=5_000_000,
        )
        current = datetime.now(timezone.utc)
        intent = Stage56SyntheticIntent(
            request_id="STAGE69-CHECK-1",
            symbol="QAABC",
            quantity=3,
            limit_price_cents=10000,
            stop_price_cents=9500,
            fee_buffer_cents=100,
        )
        quote = Stage56SyntheticQuote(
            observed_at=current,
            bid_cents=9995,
            ask_cents=10000,
            ask_depth_units=15,
            expected_slippage_bps=5,
            expected_edge_bps=40,
        )
        telemetry = Stage69UntrustedRiskTelemetry(
            daily_realized_loss_bps=0,
            current_drawdown_bps=0,
            consecutive_losses=0,
            kill_switch_active=False,
            risk_module_healthy=True,
        )
        report = inspect_stage69_synthetic_risk_budget(
            authority, intent, quote, telemetry, now=current,
        )
        status = authority.inspect()
        packet = {
            "mode": "STAGE69_DISPOSABLE_LOCAL_SYNTHETIC_QA_NO_ORDERS",
            "result": asdict(report),
            "budget_held_cents_before_and_after": status.held_cents,
            "budget_revision_before_and_after": status.revision,
        }
        print(json.dumps(packet, indent=2, sort_keys=True, allow_nan=False))
        return 0 if (
            report.local_research_preflight_passed
            and report.budget_hold_performed is False
            and report.order_submission_authorized is False
            and report.real_money_trading_enabled is False
            and report.production_ready is False
            and status.held_cents == 0 and status.revision == 0
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
