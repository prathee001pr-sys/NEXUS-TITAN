"""Stage42: isolated offline gateway-only paper account safety integration.

This is a synthetic evidence generator, never a broker adapter or market-data
client. Temporary files are deleted on exit; no user CSV/ZIP is read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from nexus_titan.shadow.paper_intent_gateway import PaperIntentDenied, PaperIntentGateway
from nexus_titan.shadow.paper_intent_evidence import (
    capture_pending_paper_intent_evidence,verify_pending_paper_intent_evidence,
)
from nexus_titan.shadow.paper_safety_preflight import inspect_paper_safety_preflight
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.durable_store import StaleAccountSnapshotError
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def run_stage42_audit() -> dict:
    with TemporaryDirectory(prefix="titan-stage42-synthetic-") as tmp:
        root=Path(tmp)

        def virtual(*, strict=False):
            return VirtualAccount(
                "STAGE42",starting_capital=50000,state_dir=root/"virtual",
                trading_mode=TradingMode.MANUAL_APPROVAL,
                require_pretrade_risk_check=True,
                approval_authorizer=lambda actor,order_id: actor=="SYNTHETIC-OWNER",
                strict_paper_mode=strict,
            )

        def research(*, guarded=False):
            return DurableResearchShadowLedger(
                root/"research.sqlite3",account_id="STAGE42",
                starting_capital=50000,guarded_paper_mode=guarded,
            )

        checks={}
        account=virtual(strict=True)
        ledger=research(guarded=True)
        checks["flat_strict_research_preflight"]=inspect_paper_safety_preflight(
            account,ledger,
        ).flat_research_gate_passed
        account.enable_gateway_only_mode(ledger)
        checks["durable_one_way_gateway_policy"]=(
            account.strict_paper_mode and account.gateway_only_mode
            and account.durable_store.gateway_only(account.account_id)
        )
        direct_denied=False
        try:
            account.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
        except PermissionError:
            direct_denied=True
        checks["direct_buy_api_denied"]=direct_denied and not account.orders

        gateway=PaperIntentGateway(account,ledger)
        refused=False
        try:
            gateway.request_buy(symbol="ABC",quantity=1,entry_price=100,
                                stop_price=95,paper_trading_enabled=False)
        except PaperIntentDenied:
            refused=True
        checks["paper_permission_default_deny"]=refused and not account.orders

        starting_cash=account.cash_balance
        buy=gateway.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        checks["buy_requires_manual_approval_no_debit"]=(
            buy.status=="PENDING_APPROVAL" and account.cash_balance==starting_cash
        )
        evidence=capture_pending_paper_intent_evidence(
            account,ledger,order_id=buy.order_id,paper_trading_enabled=True,
        )
        checks["unsigned_pending_evidence_issued"]=(
            verify_pending_paper_intent_evidence(
                evidence,account,ledger,paper_trading_enabled=True,
            )
            and not evidence.externally_signed
            and not evidence.live_trading_approved
        )

        older=virtual()
        without_approval=False
        try:
            account.execute_fill(buy.order_id,100)
        except PermissionError:
            without_approval=True
        checks["unapproved_fill_has_no_debit"]=(
            without_approval and account.cash_balance==starting_cash
        )
        initial_risk=account.risk_per_trade_pct
        account.risk_per_trade_pct=0.2
        drift_denied=False
        try:
            account.approve_order(buy.order_id,"SYNTHETIC-OWNER")
        except PermissionError:
            drift_denied=True
        checks["risk_limit_drift_rejects_approval"]=drift_denied
        account.risk_per_trade_pct=initial_risk
        account.approve_order(buy.order_id,"SYNTHETIC-OWNER")
        checks["issued_evidence_expires_after_approval"]=not verify_pending_paper_intent_evidence(
            evidence,account,ledger,paper_trading_enabled=True,
        )

        account.initial_margin_pct=25.0
        fill_drift_denied=False
        try:
            account.execute_fill(buy.order_id,100)
        except PermissionError:
            fill_drift_denied=True
        checks["margin_policy_drift_rejects_fill"]=(
            fill_drift_denied and account.cash_balance==starting_cash
        )
        account.initial_margin_pct=20.0
        account.execute_fill(buy.order_id,100,idempotency_key="STAGE42-BUY-1")
        checks["authorized_simulated_buy_and_reconcile"]=(
            account.positions["ABC"].quantity==1
            and account.reconcile().is_reconciled
        )

        old_writer_denied=False
        try:
            older.adjust_capital(100,"TOP_UP")
        except StaleAccountSnapshotError:
            old_writer_denied=True
        checks["stale_process_cannot_overwrite_positions"]=(
            old_writer_denied and older._stale_snapshot_detected
        )
        short_denied=False
        try:
            gateway.request_sell_to_close(
                symbol="ABC",quantity=2,paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            short_denied=True
        checks["naked_short_and_overclose_denied"]=short_denied
        direct_sell_denied=False
        try:
            account.submit_order("ABC","SELL",1)
        except PermissionError:
            direct_sell_denied=True
        checks["direct_sell_api_denied"]=direct_sell_denied

        close=gateway.request_sell_to_close(
            symbol="ABC",quantity=1,paper_trading_enabled=True,
        )
        checks["owned_sell_queued_manual"]=(
            close.status=="PENDING_APPROVAL" and account.positions["ABC"].quantity==1
        )
        account.approve_order(close.order_id,"SYNTHETIC-OWNER")
        account.execute_fill(close.order_id,102,idempotency_key="STAGE42-SELL-1")
        checks["owned_sell_closes_and_cash_reconciles"]=(
            not account.positions and account.reconcile().is_reconciled
        )

        recovered=virtual()
        guarded=research()
        checks["restart_restores_gateway_strict_and_risk_policy"]=(
            recovered.gateway_only_mode and recovered.strict_paper_mode
            and recovered.reconcile().is_reconciled and guarded.guarded_paper_mode
            and recovered.cash_balance==account.cash_balance
        )
        second=PaperIntentGateway(recovered,guarded).request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        recovered.approve_order(second.order_id,"SYNTHETIC-OWNER")
        recovered.execute_fill(second.order_id,100,idempotency_key="STAGE42-BUY-2")

        recovered.activate_emergency_kill_switch("offline synthetic audit")
        closed=recovered.emergency_square_off({"ABC":99})
        checks["emergency_protective_sell_remains_available"]=(
            len(closed)==1 and closed[0].state is OrderState.FILLED
            and not recovered.positions and recovered.reconcile().is_reconciled
        )

        reboot=virtual()
        checks["restart_preserves_emergency_lock"]=reboot.kill_switched
        kill_denied=False
        try:
            PaperIntentGateway(reboot,guarded).request_buy(
                symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            kill_denied=True
        checks["kill_denies_new_gateway_buy"]=kill_denied
        auto_denied=False
        try:
            reboot.set_trading_mode(TradingMode.AUTO_PAPER,actor="SYNTHETIC-OWNER")
        except PermissionError:
            auto_denied=True
        checks["strict_rejects_autopaper_even_after_restart"]=auto_denied
        checks["research_hash_audit_intact"]=guarded.verify_integrity()

        return {
            "stage":42,
            "scope":"TEMPORARY_SYNTHETIC_PAPER_ONLY",
            "checks":checks,
            "checks_passed":sum(checks.values()),
            "checks_total":len(checks),
            "all_checks_passed":all(checks.values()),
            "live_orders_transmitted":0,
            "real_market_data_approved":False,
            "cross_ledger_atomicity_verified":False,
            "externally_authenticated_identity":False,
            "automatic_strategy_promotion":False,
            "production_ready":False,
        }


def main() -> int:
    report=run_stage42_audit()
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["all_checks_passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
