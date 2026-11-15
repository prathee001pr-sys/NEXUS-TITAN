"""Stage47 synthetic research-only Risk & Veto smoke (zero broker access).

Creates only temporary virtual and research SQLite stores, no real market
history, no external HTTP requests, no strategy promotion, no paper fills.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentConfig, open_paper_only_deployment,
)
from nexus_titan.operations.offline_risk_veto import (
    Stage47OfflineRiskVetoEntry, SyntheticQuoteEvidence, SyntheticBuyProposal,
    Stage47RiskVetoBlocked,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage47-synthetic-") as name:
        root = Path(name)
        deployment = open_paper_only_deployment(
            PaperDeploymentConfig(
                account_id="STAGE47-SYNTHETIC",
                starting_capital=50000.0,
                virtual_state_dir=root / "virtual",
                research_db_path=root / "research.sqlite3",
                paper_orders_enabled=True,
            ),
            approval_authorizer=lambda actor, order_id: actor == "SYNTHETIC_OPERATOR",
        )
        now = datetime.now(timezone.utc)
        quote = SyntheticQuoteEvidence(
            observed_at=now, bid=99.95, ask=100.0,
            displayed_ask_quantity=100, expected_edge_bps=50.0,
            slippage_bps=2.0,
        )
        proposal = SyntheticBuyProposal(symbol="ABC-SYNTHETIC", quantity=1, stop_price=95)
        gate = Stage47OfflineRiskVetoEntry(deployment)
        clean = gate.inspect(proposal, quote, now=now)
        stale = gate.inspect(
            proposal, SyntheticQuoteEvidence(
                observed_at=now-timedelta(seconds=90),
                bid=99.95, ask=100.0, displayed_ask_quantity=100,
                expected_edge_bps=50.0, slippage_bps=2.0,
            ), now=now,
        )
        first = gate.request_buy(proposal, quote, now=now)
        repeat_denied = False
        try:
            gate.request_buy(proposal, quote, now=now)
        except Stage47RiskVetoBlocked:
            repeat_denied = True
        report = {
            "mode": "STAGE47_SYNTHETIC_OFFLINE_RESEARCH_ONLY",
            "risk_and_red_team_local_gate_passed": clean.new_synthetic_buy_permitted,
            "stale_quote_blocked": not stale.new_synthetic_buy_permitted,
            "manual_pending_intent_created": first.status == "PENDING_APPROVAL",
            "second_parallel_buy_blocked": repeat_denied,
            "paper_orders_filled": sum(len(o.fills) for o in deployment.virtual_account.orders.values()),
            "independent_global_risk_veto_enforced": False,
            "independent_human_identity_verified": False,
            "cross_ledger_atomicity_verified": False,
            "licensed_real_data_verified": False,
            "broker_orders_transmitted": 0,
            "production_ready": False,
            "automatic_strategy_promotion_allowed": False,
        }
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0 if all((
            report["risk_and_red_team_local_gate_passed"],
            report["stale_quote_blocked"],
            report["manual_pending_intent_created"],
            report["second_parallel_buy_blocked"],
            report["paper_orders_filled"] == 0,
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
