"""Stage77: synthetic F&O gateway integration, adversarial QA, no broker."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76UntrustedRiskTelemetry,
)
from nexus_titan.operations.stage77_brokerless_fo_sandbox import (
    Stage77BrokerlessFOSyntheticGateway, Stage77SyntheticGatewayBlocked,
)
from nexus_titan.shadow.stage75_fo_shadow_readiness import (
    Stage75FOShadowReadinessPacket, Stage75ReadinessCheck,
)

ROOT = Path(__file__).resolve().parents[1]
CAP = 1_000_000  # ₹10,000 synthetic, variable in actual functions.
DEBIT = 100_000
SHA = hashlib.sha256(b"stage77-synthetic-unverified").hexdigest()
PACKET_SHA = hashlib.sha256(b"research-idea-long-ce").hexdigest()


def packet():
    return Stage75FOShadowReadinessPacket(
        underlying="NIFTY", option_symbol="NIFTYOPT",
        selected_strike=24000.0, selected_option_type="CE",
        source_stage71_sha256=SHA, source_stage72_sha256=SHA,
        stage73_review_sha256=SHA, stage74_scenarios_sha256=SHA,
        account_id="sandbox-fo", virtual_capital_cents=CAP,
        long_option_entry_debit_cents=DEBIT,
        maximum_hypothetical_scenario_loss_cents=50_000,
        option_debit_allocation_bps_rounded_up=1000,
        maximum_scenario_loss_bps_rounded_up=500,
        research_budget_screen_passed=True,
        paired_oos_research_samples=0,
        local_chain_structurally_consistent=True,
        checks=(
            Stage75ReadinessCheck("point_in_time_research_chain", "LOCAL_RESEARCH_PASS", "operator"),
            Stage75ReadinessCheck("out_of_sample_model_review", "LOCAL_RESEARCH_PASS", "operator"),
            Stage75ReadinessCheck("long_option_scenario_accounting", "LOCAL_RESEARCH_PASS", "operator"),
            Stage75ReadinessCheck("variable_capital_stress_budget", "LOCAL_RESEARCH_PASS", "operator"),
            Stage75ReadinessCheck("global_fo_risk_capital_gate", "EXTERNAL_MISSING", "not enforced"),
            Stage75ReadinessCheck("real_fo_forward_shadow_evidence", "EXTERNAL_MISSING", "not verified"),
        ),
        blockers=(
            "GLOBAL_UNBYPASSABLE_FO_RISK_GATE_NOT_VERIFIED",
            "ATOMIC_FO_CAPITAL_RESERVATIONS_NOT_VERIFIED",
        ),
        research_packet_sha256=PACKET_SHA,
    )


def telemetry(**changes):
    default = dict(
        account_id="sandbox-fo", daily_realized_loss_bps=0,
        drawdown_bps=0, consecutive_losses=0,
        kill_switch_active=False, risk_engine_healthy=True,
    )
    default.update(changes)
    return Stage76UntrustedRiskTelemetry(**default)


def build(tmp_path, *, custom_packet=None, book_policy=None, policy=None, book=None):
    if book is None:
        book = Stage55IsolatedSyntheticExecutionBook(
            db_path=tmp_path/"stage77_synthetic.sqlite",
            account_id="sandbox-fo", starting_cents=CAP,
            policy=book_policy or Stage55SyntheticPolicy(
                max_single_reserve_bps=2000, max_open_reserve_bps=4500,
            ),
        )
    gateway = Stage77BrokerlessFOSyntheticGateway(
        book=book, research_packets=(custom_packet or packet(),),
        policy=policy or Stage76FOResearchPolicy(),
    )
    return gateway, book


def reserve(gateway, **changes):
    args = dict(
        research_packet_sha256=PACKET_SHA, request_id="fo-order-1",
        symbol="NIFTYOPT", lots=1, lot_size=25,
        limit_price_cents=3992, fee_buffer_cents=200,
        telemetry=telemetry(),
    )
    args.update(changes)
    return gateway.reserve_synthetic_long_option(**args)


def test_single_sqlite_hold_partial_fill_full_fill_conserves_cash(tmp_path):
    gateway, book = build(tmp_path)
    receipt = reserve(gateway)
    assert receipt.action == "SYNTHETIC_RESERVE_ONLY"
    assert receipt.order_state == "PENDING_SYNTHETIC"
    assert receipt.event_revision == 1
    assert receipt.reserved_cents_after == DEBIT
    assert receipt.available_cents_after == CAP-DEBIT
    first = gateway.record_synthetic_fill(
        request_id="fo-order-1", fill_id="fill1", quantity=10,
        price_cents=3900, fee_cents=50, telemetry=telemetry(),
    )
    assert first.order_state == "PARTIAL_SYNTHETIC"
    assert first.event_revision == 2
    last = gateway.record_synthetic_fill(
        request_id="fo-order-1", fill_id="fill2", quantity=15,
        price_cents=3890, fee_cents=70, telemetry=telemetry(),
    )
    assert last.order_state == "FILLED_SYNTHETIC"
    assert last.reserved_cents_after == 0
    status = book.inspect()
    assert status.local_integrity_verified
    assert status.cash_cents == CAP-(10*3900+50)-(15*3890+70)
    assert status.available_cents == status.cash_cents
    assert status.paid_fees_cents == 120
    assert status.filled_orders == 1
    assert last.paper_order_authorized is False
    assert last.global_legacy_entrypoints_fenced is False
    assert last.live_trading_enabled is False
    assert last.broker_orders_transmitted == 0
    assert last.verdict.endswith("NO_GO")


def test_cancel_releases_pending_reserve_under_kill_switch(tmp_path):
    gateway, book = build(tmp_path)
    reserve(gateway)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Risk gate denies"):
        gateway.record_synthetic_fill(
            request_id="fo-order-1", fill_id="blocked", quantity=1,
            price_cents=3900, fee_cents=0,
            telemetry=telemetry(kill_switch_active=True),
        )
    assert book.inspect().revision == 1
    cancelled = gateway.cancel_synthetic_remaining(
        request_id="fo-order-1", cancel_id="cancel1",
    )
    assert cancelled.order_state == "CANCELLED_SYNTHETIC"
    assert cancelled.reserved_cents_after == 0
    assert cancelled.available_cents_after == CAP
    assert book.inspect().cancelled_orders == 1
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Unknown"):
        gateway.cancel_synthetic_remaining(
            request_id="fo-order-1", cancel_id="cancel2",
        )


@pytest.mark.parametrize("pulse", [
    telemetry(kill_switch_active=True),
    telemetry(risk_engine_healthy=False),
    telemetry(daily_realized_loss_bps=300),
    telemetry(drawdown_bps=1000),
    telemetry(consecutive_losses=3),
])
def test_bad_risk_recheck_never_mutates_book(tmp_path, pulse):
    gateway, book = build(tmp_path)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Risk gate denies"):
        reserve(gateway, telemetry=pulse)
    assert book.inspect().revision == 0
    assert book.inspect().open_reserved_cents == 0


def test_duplicate_orders_and_simulated_fill_ids_fail_closed(tmp_path):
    gateway, book = build(tmp_path)
    reserve(gateway)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="duplicate request"):
        reserve(gateway)
    gateway.record_synthetic_fill(
        request_id="fo-order-1", fill_id="fill1", quantity=5,
        price_cents=3900, fee_cents=10, telemetry=telemetry(),
    )
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="simulated fill failed"):
        gateway.record_synthetic_fill(
            request_id="fo-order-1", fill_id="fill1", quantity=5,
            price_cents=3900, fee_cents=10, telemetry=telemetry(),
        )
    assert book.inspect().revision == 2


@pytest.mark.parametrize("changes", [
    {"symbol": "BANKNIFTYOPT"},
    {"lots": 0},
    {"lot_size": True},
    {"limit_price_cents": 4000},
    {"fee_buffer_cents": -1},
    {"request_id": "bad|request"},
    {"research_packet_sha256": "bad"},
])
def test_invalid_contract_lots_or_debit_never_hold(tmp_path, changes):
    gateway, book = build(tmp_path)
    with pytest.raises(Stage77SyntheticGatewayBlocked):
        reserve(gateway, **changes)
    assert book.inspect().revision == 0


def test_oversized_single_book_reservation_rejected_transactionally(tmp_path):
    # Stage76 accepts the disclosed 25% research cap but Stage55 cap is 20%.
    p = replace(packet(), long_option_entry_debit_cents=220_000,
                option_debit_allocation_bps_rounded_up=2200,
                maximum_hypothetical_scenario_loss_cents=50_000,
                maximum_scenario_loss_bps_rounded_up=500)
    gateway, book = build(tmp_path, custom_packet=p)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Single-DB synthetic capital reserve rejected"):
        reserve(gateway, limit_price_cents=8792, fee_buffer_cents=200)
    assert book.inspect().revision == 0


def test_forged_stage75_approval_or_inconsistent_budget_rejected(tmp_path):
    for forged in (
        replace(packet(), live_trading_enabled=True),
        replace(packet(), global_risk_veto_unbypassable=True),
        replace(packet(), option_debit_allocation_bps_rounded_up=999),
    ):
        directory = tmp_path / hashlib.sha256(repr(forged).encode()).hexdigest()[:10]
        gateway, book = build(directory, custom_packet=forged)
        with pytest.raises(Stage77SyntheticGatewayBlocked):
            reserve(gateway)
        assert book.inspect().revision == 0


def test_incompatible_sqlite_policy_is_not_silently_accepted(tmp_path):
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="reserve caps"):
        build(tmp_path, book_policy=Stage55SyntheticPolicy())


def test_restart_with_pending_order_is_fail_closed_no_unsafe_adoption(tmp_path):
    gateway, book = build(tmp_path)
    reserve(gateway)
    reopened = Stage55IsolatedSyntheticExecutionBook(
        db_path=tmp_path/"stage77_synthetic.sqlite",
        account_id="sandbox-fo", starting_cents=CAP,
        policy=Stage55SyntheticPolicy(
            max_single_reserve_bps=2000, max_open_reserve_bps=4500,
        ),
    )
    assert reopened.inspect().open_reserved_cents == DEBIT
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="manual recovery"):
        build(tmp_path, book=reopened)
    assert reopened.inspect().revision == 1


def test_cross_account_or_capital_mismatch_is_never_adopted(tmp_path):
    p = replace(packet(), virtual_capital_cents=CAP+100)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="capital differs"):
        build(tmp_path, custom_packet=p)


def test_corrupted_local_sqlite_head_blocks_all_mutations(tmp_path):
    gateway, book = build(tmp_path)
    reserve(gateway)
    with sqlite3.connect(tmp_path/"stage77_synthetic.sqlite") as conn:
        conn.execute("UPDATE execution_head SET cash_cents=cash_cents-1")
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="journal"):
        gateway.cancel_synthetic_remaining(
            request_id="fo-order-1", cancel_id="cancel1",
        )
    assert not book.inspect().local_integrity_verified


def test_no_real_execution_claims_and_no_input_cli(tmp_path):
    gateway, _ = build(tmp_path)
    result = reserve(gateway)
    for flag in (
        "risk_telemetry_independently_authenticated",
        "global_legacy_entrypoints_fenced",
        "real_exchange_data_authenticated",
        "single_global_atomic_capital_authority_verified",
        "owner_identity_authenticated", "paper_order_authorized",
        "strategy_promotion_authorized", "live_trading_enabled",
    ):
        assert getattr(result, flag) is False
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage77_fo_gateway_smoke.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    info = json.loads(p.stdout)
    assert info["mode"] == "STAGE77_NO_INPUT_SYNTHETIC_GATEWAY"
    assert info["broker_orders_transmitted"] == 0
    assert not info["globally_mandatory_risk_enforcement"]
