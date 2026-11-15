"""Stage39: brokerless adversarial end-to-end safety audit.

Uses ONLY temporary synthetic accounts. It does not download source data,
contact an exchange or broker, sign identity proofs or authorize live orders.
An all-green result is an isolated research quality gate, NOT production.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from nexus_titan.shadow.paper_intent_gateway import PaperIntentDenied,PaperIntentGateway
from nexus_titan.shadow.paper_intent_evidence import (
    capture_pending_paper_intent_evidence,verify_pending_paper_intent_evidence,
)
from nexus_titan.shadow.paper_safety_preflight import inspect_paper_safety_preflight
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.durable_store import StaleAccountSnapshotError
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def run_strict_synthetic_audit() -> dict:
    with TemporaryDirectory(prefix="nexus-titan-stage39-") as tmp:
        root=Path(tmp)
        def make_virtual(*, strict=False):
            return VirtualAccount(
                "STAGE39-SYNTHETIC",starting_capital=50000,
                require_pretrade_risk_check=True,
                trading_mode=TradingMode.MANUAL_APPROVAL,
                approval_authorizer=lambda actor,oid: actor=="SIMULATED-OWNER",
                state_dir=root/"virtual",strict_paper_mode=strict,
            )
        def make_research(*, guarded=False):
            return DurableResearchShadowLedger(
                root/"research.sqlite3",account_id="STAGE39-SYNTHETIC",
                starting_capital=50000,guarded_paper_mode=guarded,
            )

        account=make_virtual(strict=True)
        research=make_research(guarded=True)
        gateway=PaperIntentGateway(account,research)
        check={}
        check["strict_policy_saved_before_first_order"] = (
            account.durable_store.strict_mode(account.account_id)
            and account._snapshot_revision == 1
        )
        check["research_guarded_and_audited"] = (
            research.guarded_paper_mode and research.verify_integrity()
        )
        check["initial_flat_preflight"] = inspect_paper_safety_preflight(
            account,research
        ).flat_research_gate_passed
        before=account.cash_balance
        denied=False
        try:
            gateway.request_buy(
                symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                paper_trading_enabled=False,
            )
        except PaperIntentDenied:
            denied=True
        check["default_paper_permission_denied_without_debit"] = (
            denied and account.cash_balance==before and account.orders=={}
        )
        pending=gateway.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        check["manual_pending_buy_no_cash_debit"] = (
            pending.status=="PENDING_APPROVAL" and account.cash_balance==before
        )
        ev=capture_pending_paper_intent_evidence(
            account,research,order_id=pending.order_id,
            paper_trading_enabled=True,
        )
        check["unsigned_intent_evidence_valid_at_issue"] = (
            not ev.externally_signed and not ev.authenticated_identity
            and not ev.live_trading_approved
            and verify_pending_paper_intent_evidence(
                ev,account,research,paper_trading_enabled=True
            )
        )
        old_handle=make_virtual()
        denied_unapproved=False
        try:
            account.execute_fill(pending.order_id,100)
        except PermissionError:
            denied_unapproved=True
        check["unapproved_fill_blocked_without_debit"] = (
            denied_unapproved and account.cash_balance==before
        )
        account.approve_order(pending.order_id,"SIMULATED-OWNER")
        check["receipt_stale_after_approval"] = not verify_pending_paper_intent_evidence(
            ev,account,research,paper_trading_enabled=True,
        )
        account.execute_fill(pending.order_id,100,idempotency_key="S39-BUY-1")
        check["approved_paper_buy_has_one_owned_position"] = (
            account.positions["ABC"].quantity==1
            and account.reconcile().is_reconciled
        )
        stale_rejected=False
        try:
            old_handle.submit_order(
                "XYZ","BUY",1,entry_price=100,stop_price=95
            )
        except StaleAccountSnapshotError:
            stale_rejected=True
        check["old_process_snapshot_cannot_overwrite_newer_buy"] = (
            stale_rejected and old_handle._stale_snapshot_detected
        )
        no_short=False
        try:
            gateway.request_sell_to_close(
                symbol="ABC",quantity=2,paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            no_short=True
        check["naked_or_overquantity_sell_denied"] = no_short
        sell=gateway.request_sell_to_close(
            symbol="ABC",quantity=1,paper_trading_enabled=True,
        )
        check["sell_pending_manual_not_filled"] = (
            sell.status=="PENDING_APPROVAL"
            and account.positions["ABC"].quantity==1
        )
        double_close_denied=False
        try:
            gateway.request_sell_to_close(
                symbol="ABC",quantity=1,paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            double_close_denied=True
        check["duplicate_pending_sell_denied"] = double_close_denied
        sell_without_approval=False
        try:
            account.execute_fill(sell.order_id,105)
        except PermissionError:
            sell_without_approval=True
        check["unapproved_sell_fill_blocked"] = sell_without_approval
        account.approve_order(sell.order_id,"SIMULATED-OWNER")
        account.execute_fill(sell.order_id,105,idempotency_key="S39-SELL-1")
        check["closed_trade_reconciles_without_inventory"] = (
            not account.positions and account.reconcile().is_reconciled
        )
        restored=make_virtual()
        replayed=make_research()
        check["restart_keeps_strict_policy_and_reconciled_cash"] = (
            restored.strict_paper_mode and replayed.guarded_paper_mode
            and restored.reconcile().is_reconciled
            and restored.cash_balance==account.cash_balance
        )
        next_buy=PaperIntentGateway(restored,replayed).request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=True,
        )
        restored.approve_order(next_buy.order_id,"SIMULATED-OWNER")
        restored.execute_fill(next_buy.order_id,100,idempotency_key="S39-BUY-2")
        stale_after_buy=make_virtual()
        restored.activate_emergency_kill_switch("synthetic security audit")
        exits=restored.emergency_square_off({"ABC":99})
        check["emergency_sells_owned_long_without_live_order"] = (
            len(exits)==1 and exits[0].is_emergency
            and exits[0].state is OrderState.FILLED
            and restored.positions=={}
        )
        locked=make_virtual()
        check["kill_lock_survives_restart_and_reconciles"] = (
            locked.kill_switched and locked.reconcile().is_reconciled
        )
        stale_kill_rejected=False
        try:
            stale_after_buy.emergency_square_off({"ABC":99})
        except StaleAccountSnapshotError:
            stale_kill_rejected=True
        check["stale_emergency_handle_must_recover"] = stale_kill_rejected
        kill_buy_denied=False
        try:
            PaperIntentGateway(locked,replayed).request_buy(
                symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                paper_trading_enabled=True,
            )
        except PaperIntentDenied:
            kill_buy_denied=True
        check["kill_blocks_new_gateway_buys"] = kill_buy_denied
        auto_mode_denied=False
        try:
            locked.set_trading_mode(TradingMode.AUTO_PAPER,actor="SIMULATED-OWNER")
        except PermissionError:
            auto_mode_denied=True
        check["strict_mode_never_escalates_to_auto"] = auto_mode_denied
        check["research_guard_hash_chain_retained"] = replayed.verify_integrity()
        report={
            "stage":39,
            "environment":"ISOLATED_SYNTHETIC_RESEARCH_ONLY",
            "starting_virtual_capital":50000,
            "checks":check,
            "checks_total":len(check),
            "checks_passed":sum(check.values()),
            "all_checks_passed":all(check.values()),
            "global_order_router_verified":False,
            "cross_ledger_atomicity_verified":False,
            "externally_authenticated_approvals":False,
            "real_fo_historical_data_verified":False,
            "live_broker_orders_transmitted":0,
            "automatic_strategy_promotion":False,
            "production_ready":False,
        }
        return report


def main() -> int:
    result=run_strict_synthetic_audit()
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["all_checks_passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
