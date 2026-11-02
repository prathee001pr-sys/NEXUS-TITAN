"""Stage36: offline, temporary-account end-to-end *synthetic* paper safety audit.

NEVER reads uploaded user data, never contacts a broker, network or GitHub.
Writes only inside a temporary directory and prints JSON evidence at the end.
Does not run a genuine historical market backtest or shadow live trading.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from nexus_titan.shadow.paper_intent_gateway import PaperIntentGateway,PaperIntentDenied
from nexus_titan.shadow.paper_intent_evidence import (
    capture_pending_paper_intent_evidence,verify_pending_paper_intent_evidence,
)
from nexus_titan.shadow.paper_safety_preflight import inspect_paper_safety_preflight
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger,ResearchLedgerError
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def run_synthetic_audit() -> dict:
    with tempfile.TemporaryDirectory(prefix="titan-stage36-offline-") as temp:
        root=Path(temp)
        def make_virtual():
            return VirtualAccount(
                "STAGE36-SYNTH",starting_capital=50000,
                require_pretrade_risk_check=True,
                trading_mode=TradingMode.MANUAL_APPROVAL,
                approval_authorizer=lambda actor,oid: actor=="SYNTHETIC-OWNER",
                state_dir=root/"virtual",
            )
        def make_ledger():
            return DurableResearchShadowLedger(
                root/"research.sqlite3",account_id="STAGE36-SYNTH",
                starting_capital=50000,
                # Constructor without guard intentionally tests non-downgrade
                # after first initialization.
                guarded_paper_mode=not (root/"research.sqlite3").exists(),
            )

        virtual=make_virtual()
        research=make_ledger()
        gateway=PaperIntentGateway(virtual,research)
        start=inspect_paper_safety_preflight(virtual,research)
        if not start.flat_research_gate_passed:
            raise RuntimeError("Initial synthetic preflight failed: "+str(start.blockers))
        rejected_permission=False
        try:
            gateway.request_buy(
                symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                paper_trading_enabled=False,
            )
        except PaperIntentDenied:
            rejected_permission=True
        buy=gateway.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        evidence=capture_pending_paper_intent_evidence(
            virtual,research,order_id=buy.order_id,paper_trading_enabled=True,
        )
        evidence_initially_valid=verify_pending_paper_intent_evidence(
            evidence,virtual,research,paper_trading_enabled=True,
        )
        virtual.approve_order(buy.order_id,"SYNTHETIC-OWNER")
        evidence_stale_after_approval=not verify_pending_paper_intent_evidence(
            evidence,virtual,research,paper_trading_enabled=True,
        )
        virtual.execute_fill(buy.order_id,100,idempotency_key="stage36-buy-1")
        assert virtual.positions["ABC"].quantity==1
        denied_naked_sell=False
        try:
            gateway.request_sell_to_close(
                symbol="ABC",quantity=2,paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            denied_naked_sell=True
        sell=gateway.request_sell_to_close(
            symbol="ABC",quantity=1,paper_trading_enabled=True,
        )
        virtual.approve_order(sell.order_id,"SYNTHETIC-OWNER")
        virtual.execute_fill(sell.order_id,103,idempotency_key="stage36-sell-1")
        closing_reconciled=virtual.reconcile().is_reconciled and not virtual.positions
        restored=make_virtual()
        reopened=make_ledger()
        restart_reconciled=restored.reconcile().is_reconciled
        guarded_not_downgraded=reopened.guarded_paper_mode
        # After synthetic round-trip no residual open risk; second BUY allowed.
        second_gateway=PaperIntentGateway(restored,reopened)
        second=second_gateway.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        restored.approve_order(second.order_id,"SYNTHETIC-OWNER")
        restored.execute_fill(second.order_id,100,idempotency_key="stage36-buy-2")
        restored.activate_emergency_kill_switch("Synthetic E2E emergency test")
        closed=restored.emergency_square_off({"ABC":99})
        locked=make_virtual()
        post_kill_denied=False
        try:
            PaperIntentGateway(locked,reopened).request_buy(
                symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            post_kill_denied=True
        direct_reserve_denied=False
        from datetime import date,datetime
        from nexus_titan.data.instrument_master import PointInTimeContractSpec
        synthetic_contract=PointInTimeContractSpec(
            symbol="NIFTYOPT",underlying="NIFTY",exchange="NSE",segment="OPTIONS",
            lot_size=25,tick_size=0.05,freeze_quantity=1000,max_lots_per_trade=10,
            strike_step=50.0,expiry_date=date(2026,11,5),
            effective_from=date(2026,11,1),effective_to=date(2026,11,5),
            source_reference="synthetic/no-vendor-authentication",source_verified=True,
        )
        try:
            reopened.reserve_buy(
                order_id="UNAUTHORIZED",contract=synthetic_contract,
                strike=100,option_type="CE",lots=1,
                as_of=datetime.fromisoformat("2026-11-02T09:16:00+05:30"),
                max_unit_premium=6,fee_buffer=25,
            )
        except ResearchLedgerError as exc:
            direct_reserve_denied="atomic risk admission" in str(exc)
        checks={
            "default_paper_permission_denied":rejected_permission,
            "initial_flat_preflight":start.flat_research_gate_passed,
            "buy_pending_manual":buy.status=="PENDING_APPROVAL",
            "intent_evidence_valid_at_issue":evidence_initially_valid,
            "intent_evidence_expires_after_approval":evidence_stale_after_approval,
            "naked_sell_denied":denied_naked_sell,
            "close_pending_manual":sell.status=="PENDING_APPROVAL",
            "cash_positions_reconciled_after_close":closing_reconciled,
            "durable_restart_reconciled":restart_reconciled,
            "research_guard_cannot_downgrade":guarded_not_downgraded,
            "research_audit_intact":reopened.verify_integrity(),
            "emergency_sell_closes_position":len(closed)==1 and not restored.positions,
            "kill_switch_survives_restart":locked.kill_switched,
            "gateway_buy_denied_after_kill":post_kill_denied,
            "research_direct_reserve_denied":direct_reserve_denied,
            "post_emergency_reconciled":locked.reconcile().is_reconciled,
        }
        return {
            "stage":36,"mode":"SYNTHETIC_OFFLINE_RESEARCH_ONLY",
            "starting_capital":50000,"checks":checks,
            "checks_passed":sum(checks.values()),
            "checks_total":len(checks),
            "all_checks_passed":all(checks.values()),
            "genuine_fo_market_data_verified":False,
            "real_broker_trading_enabled":False,
            "global_order_router_proven":False,
            "production_ready":False,
            "strategy_promotion_approved":False,
        }


def main() -> int:
    report=run_synthetic_audit()
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["all_checks_passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
