"""Stage64: fully synthetic, non-broker NIFTY/BANKNIFTY trial governance smoke.

All daily figures are fabricated and intentionally profitable so that local
KPI thresholds can PASS without changing NO-GO real-data/identity/risk flags.
No exchange history, authenticated event ledger, cash DB or actual order.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.operations.integration_candidate_audit import inspect_stage62_candidate
from nexus_titan.research.stage61_evidence_scorecard import inspect_stage61_fo_evidence
from nexus_titan.shadow.stage64_trial_governance import (
    Stage64DailyClaim, Stage64TrialPlan, inspect_stage64_shadow_trial,
)
from scripts.run_stage61_fo_evidence_smoke import _inputs


CAL = nse_equity_derivatives_baseline()
START = date(2026, 9, 1)
END = date(2026, 9, 28)
CAPITAL_CENTS = 3_500_000  # 35,000 rupees, intentionally NOT a fixed ₹50k rule


def _trial(underlying: str = "NIFTY", *, starting_capital: int = CAPITAL_CENTS):
    plan = Stage64TrialPlan(
        trial_id="STAGE64-QA-" + underlying,
        account_id="QA-NO-BROKER-" + underlying,
        strategy_version="FIXED-EXPLORATORY-NOT-APPROVED-v1",
        underlying=underlying,
        registered_at=datetime.fromisoformat("2026-08-31T18:00:00+05:30"),
        start_date=START, end_date=END,
        starting_capital_cents=starting_capital,
    )
    current = START
    cash = starting_capital
    records = []
    while current <= END:
        if CAL.is_trading_day(current):
            after_close = datetime.combine(
                current, datetime.min.time(), CAL.zone
            ) + timedelta(hours=16)
            win_cents, loss_cents, fee_cents, slip_cents = 3000, 1000, 200, 100
            close = cash + win_cents - loss_cents - fee_cents - slip_cents
            records.append(Stage64DailyClaim(
                session_date=current, observed_at=after_close,
                account_id=plan.account_id, underlying=underlying,
                source_class="FABRICATED_QA",
                opening_cash_cents=cash, closing_cash_cents=close,
                gross_winning_cents=win_cents,
                gross_losing_cents=loss_cents,
                fees_cents=fee_cents, slippage_cents=slip_cents,
                closed_trades=2, winning_trades=1,
                losing_trades=1, flat_trades=0,
                execution_observations=4, missing_market_observations=0,
                risk_limit_breaches=0, unresolved_orders=0,
                unvalued_open_positions=0,
                claimed_max_intraday_drawdown_bps=100,
                data_quality_checked=True, paper_orders_reconciled=True,
                evidence_reference="qa/unverified-day-" + current.isoformat(),
            ))
            cash = close
        current += timedelta(days=1)
    return plan, tuple(records)


def _scorecard(tmp: Path, underlying: str, integration):
    hist, oos, execution = _inputs(tmp / underlying.lower(), underlying)
    fo = inspect_stage61_fo_evidence(hist, oos, execution=execution)
    plan, days = _trial(underlying)
    report = inspect_stage64_shadow_trial(
        plan, days, calendar=CAL,
        as_of=datetime.fromisoformat("2026-09-29T12:00:00+05:30"),
        fo_evidence=fo, integration=integration,
    )
    return {
        "underlying": report.underlying,
        "starting_capital_cents": plan.starting_capital_cents,
        "supplied_sessions": report.supplied_sessions,
        "expected_trading_sessions": report.expected_trading_sessions,
        "missing_trading_sessions": len(report.missing_session_dates),
        "declared_closed_trades": report.declared_closed_trades,
        "claimed_net_pnl_cents": report.claimed_net_pnl_cents,
        "claimed_gross_profit_factor": str(report.claimed_gross_profit_factor),
        "claimed_net_expectancy_cents": str(report.claimed_net_expectancy_cents),
        "local_trial_criteria_met": report.local_trial_criteria_met,
        "local_trial_sha256": report.local_trial_sha256,
        "mandatory_external_blockers": list(report.mandatory_external_blockers),
        "authentic_real_shadow_performance": report.genuine_net_pnl_verified,
        "strategy_promotion_authorized": report.strategy_promotion_authorized,
        "live_trading_enabled": report.live_trading_enabled,
        "production_ready": report.production_ready,
        "broker_orders_transmitted": report.broker_orders_transmitted,
    }


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage64-qa-only-") as d:
        root = Path(d)
        snapshot = json.loads(
            (ROOT / "docs" / "STAGE62_PR_DEPENDENCY_SNAPSHOT_2026-11-03.json").read_text(
                encoding="utf-8"
            )
        )
        stage62 = inspect_stage62_candidate(ROOT, pr_snapshot=snapshot)
        output = {
            "mode": "STAGE64_FABRICATED_TRIAL_GOVERNANCE_NO_GO_ONLY",
            "nifty": _scorecard(root, "NIFTY", stage62),
            "banknifty": _scorecard(root, "BANKNIFTY", stage62),
            "data_source_is_real_market": False,
            "real_broker_fills": False,
            "signed_trials_registered": False,
            "live_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
        return 0 if all(
            output[k]["local_trial_criteria_met"]
            and output[k]["supplied_sessions"] == 20
            and output[k]["declared_closed_trades"] == 40
            and not output[k]["authentic_real_shadow_performance"]
            and not output[k]["strategy_promotion_authorized"]
            and not output[k]["production_ready"]
            and len(output[k]["mandatory_external_blockers"]) >= 8
            for k in ("nifty", "banknifty")
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
