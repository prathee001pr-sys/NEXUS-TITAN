"""Stage79: guard local Stage55 SQLite writes against stale Stage77 risk snapshots.

These are synthetic race/replay tests. Exact-head CAS is OPTIONAL on raw
Stage55 APIs, so it is NOT an independently enforced global Risk & Veto.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,
    Stage55SyntheticBookBlocked, Stage55SyntheticPolicy,
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
CAP = 1_000_000
H = hashlib.sha256(b"synthetic-stage79-unverified").hexdigest()
PH = hashlib.sha256(b"stage79-research-only-packet").hexdigest()


def book(path: Path):
    return Stage55IsolatedSyntheticExecutionBook(
        db_path=path, account_id="stage79-qa",
        starting_cents=CAP,
        policy=Stage55SyntheticPolicy(
            max_single_reserve_bps=2000, max_open_reserve_bps=4500,
        ),
    )


def _open(b, order="other", *, expected_revision=None, expected_journal_tip=None):
    return b.reserve_synthetic_buy(
        request_id=order, symbol="NIFTYOPT", quantity=25,
        limit_price_cents=1000, fee_buffer_cents=0,
        expected_revision=expected_revision,
        expected_journal_tip=expected_journal_tip,
    )


def synthetic_packet():
    checks = (
        Stage75ReadinessCheck("point_in_time_research_chain", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("out_of_sample_model_review", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("long_option_scenario_accounting", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("variable_capital_stress_budget", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("global_fo_risk_capital_gate", "EXTERNAL_MISSING", "not global"),
        Stage75ReadinessCheck("real_fo_forward_shadow_evidence", "EXTERNAL_MISSING", "no verified feed"),
    )
    return Stage75FOShadowReadinessPacket(
        underlying="NIFTY", option_symbol="NIFTYOPT",
        selected_strike=24000., selected_option_type="CE",
        source_stage71_sha256=H, source_stage72_sha256=H,
        stage73_review_sha256=H, stage74_scenarios_sha256=H,
        account_id="stage79-qa", virtual_capital_cents=CAP,
        long_option_entry_debit_cents=100_000,
        maximum_hypothetical_scenario_loss_cents=50_000,
        option_debit_allocation_bps_rounded_up=1000,
        maximum_scenario_loss_bps_rounded_up=500,
        research_budget_screen_passed=True, paired_oos_research_samples=0,
        local_chain_structurally_consistent=True, checks=checks,
        blockers=(
            "GLOBAL_UNBYPASSABLE_FO_RISK_GATE_NOT_VERIFIED",
            "ATOMIC_FO_CAPITAL_RESERVATIONS_NOT_VERIFIED",
        ),
        research_packet_sha256=PH,
    )


def pulse(**changes):
    attrs = dict(
        account_id="stage79-qa", daily_realized_loss_bps=0,
        drawdown_bps=0, consecutive_losses=0,
        kill_switch_active=False, risk_engine_healthy=True,
    )
    attrs.update(changes)
    return Stage76UntrustedRiskTelemetry(**attrs)


def gateway(path):
    local = book(path)
    gate = Stage77BrokerlessFOSyntheticGateway(
        book=local, research_packets=(synthetic_packet(),),
        policy=Stage76FOResearchPolicy(),
    )
    return gate, local


def reserve(gate):
    return gate.reserve_synthetic_long_option(
        research_packet_sha256=PH, request_id="stage79-intent",
        symbol="NIFTYOPT", lots=1, lot_size=25, limit_price_cents=3992,
        fee_buffer_cents=200, telemetry=pulse(),
    )


def test_exact_head_CAS_supports_synthetic_open_fill_cancel(tmp_path):
    b = book(tmp_path / "single.db")
    before = b.inspect()
    opened = _open(
        b, order="order-one", expected_revision=before.revision,
        expected_journal_tip=before.journal_tip,
    )
    assert opened.revision == 1
    assert opened.open_reserved_cents == 25000
    filled = b.record_simulated_fill(
        order_id="order-one", fill_id="fill-one",
        quantity=10, price_cents=980, fee_cents=0,
        evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        expected_revision=opened.revision,
        expected_journal_tip=opened.journal_tip,
    )
    assert filled.revision == 2
    assert filled.order_state == "PARTIAL_SYNTHETIC"
    cancelled = b.cancel_unfilled(
        order_id="order-one", cancel_id="cancel-one",
        evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        expected_revision=filled.revision,
        expected_journal_tip=filled.journal_tip,
    )
    assert cancelled.revision == 3
    assert cancelled.order_state == "CANCELLED_SYNTHETIC"
    assert cancelled.open_reserved_cents == 0
    assert b.inspect().local_integrity_verified


@pytest.mark.parametrize("partial", [
    {"expected_revision": 0},
    {"expected_journal_tip": "0"*64},
    {"expected_revision": True, "expected_journal_tip": "0"*64},
    {"expected_revision": -1, "expected_journal_tip": "0"*64},
    {"expected_revision": 0, "expected_journal_tip": "BAD"},
])
def test_incomplete_or_bad_head_is_rejected_before_write(tmp_path, partial):
    b = book(tmp_path / "single.db")
    with pytest.raises(Stage55SyntheticBookBlocked, match="supplied together|Invalid expected"):
        _open(b, order="new", **partial)
    assert b.inspect().revision == 0


def test_stale_snapshot_denied_under_single_SQLite_atomic_transaction(tmp_path):
    path = tmp_path / "shared.db"
    a, b = book(path), book(path)
    old = a.inspect()
    _open(b, order="other-writer")
    with pytest.raises(Stage55SyntheticBookBlocked, match="Stale synthetic SQLite snapshot"):
        _open(a, order="fresh-intent-but-stale-evidence",
              expected_revision=old.revision,
              expected_journal_tip=old.journal_tip)
    status = a.inspect()
    assert status.local_integrity_verified
    assert status.revision == 1
    assert status.total_orders == 1


def test_same_revision_wrong_journal_tip_denied(tmp_path):
    b = book(tmp_path / "single.db")
    old = b.inspect()
    with pytest.raises(Stage55SyntheticBookBlocked, match="Stale synthetic SQLite snapshot"):
        _open(b, order="forged", expected_revision=0,
              expected_journal_tip="a"*64)
    assert old == b.inspect()


def test_gateway_recognizes_external_direct_writer_before_risk_review(tmp_path):
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    external = book(path)
    _open(external, order="direct-legacy")
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Unexpected direct SQLite"):
        reserve(gate)
    assert local.inspect().revision == 1
    assert local.inspect().open_reserved_cents == 25000


def test_gateway_CAS_denies_direct_writer_between_snapshot_and_reserve(tmp_path, monkeypatch):
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    external = book(path)
    original = local.reserve_synthetic_buy
    injected = []

    def competing_write(**kwargs):
        if not injected:
            injected.append(_open(external, order="racing-legacy").revision)
        return original(**kwargs)

    monkeypatch.setattr(local, "reserve_synthetic_buy", competing_write)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Single-DB synthetic capital reserve rejected"):
        reserve(gate)
    assert injected == [1]
    assert local.inspect().local_integrity_verified
    assert local.inspect().total_orders == 1
    assert local.inspect().open_reserved_cents == 25000
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Unexpected direct SQLite"):
        reserve(gate)


def test_gateway_CAS_denies_direct_writer_between_snapshot_and_fill(tmp_path, monkeypatch):
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    reserve(gate)
    external = book(path)
    original = local.record_simulated_fill
    injected = []

    def racing_fill(**kwargs):
        if not injected:
            injected.append(_open(external, order="racing-intent").revision)
        return original(**kwargs)

    monkeypatch.setattr(local, "record_simulated_fill", racing_fill)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Single-DB simulated fill failed"):
        gate.record_synthetic_fill(
            request_id="stage79-intent", fill_id="stage79-fill",
            quantity=25, price_cents=3900, fee_cents=200,
            telemetry=pulse(),
        )
    assert injected == [2]
    assert local.inspect().revision == 2
    assert local.inspect().filled_orders == 0
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Unexpected direct SQLite"):
        gate.record_synthetic_fill(
            request_id="stage79-intent", fill_id="second-fill",
            quantity=25, price_cents=3900, fee_cents=200,
            telemetry=pulse(),
        )


def test_gateway_CAS_denies_cancel_while_direct_writer_changes_revision(tmp_path, monkeypatch):
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    reserve(gate)
    external = book(path)
    original = local.cancel_unfilled
    injected = []

    def racing_cancel(**kwargs):
        if not injected:
            injected.append(_open(external, order="racing-cancel").revision)
        return original(**kwargs)

    monkeypatch.setattr(local, "cancel_unfilled", racing_cancel)
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Synthetic cancellation failed"):
        gate.cancel_synthetic_remaining(request_id="stage79-intent", cancel_id="cancel")
    assert injected == [2]
    assert local.inspect().revision == 2
    assert local.inspect().cancelled_orders == 0


def test_normal_gateway_partial_fill_cancel_continues_to_succeed(tmp_path):
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    open_receipt = reserve(gate)
    assert open_receipt.event_revision == 1
    assert open_receipt.reserved_cents_after == 100000
    partial = gate.record_synthetic_fill(
        request_id="stage79-intent", fill_id="part-one",
        quantity=10, price_cents=3900, fee_cents=50, telemetry=pulse(),
    )
    assert partial.event_revision == 2
    cancel = gate.cancel_synthetic_remaining(
        request_id="stage79-intent", cancel_id="cancel-rest",
    )
    assert cancel.event_revision == 3
    assert cancel.reserved_cents_after == 0
    assert local.inspect().local_integrity_verified
    assert local.inspect().cash_cents == CAP - 10*3900 - 50


def test_local_CAS_does_not_close_raw_legacy_bypass(tmp_path):
    """Negative proof: Stage55 still allows writes without optional head CAS."""
    path = tmp_path / "shared.db"
    gate, local = gateway(path)
    assert gate._expected_revision == 0
    external = book(path)
    receipt = _open(external, order="legacy-api-direct")
    assert receipt.revision == 1
    assert receipt.trading_authority is False
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Unexpected direct SQLite"):
        reserve(gate)


def test_stage79_safety_smoke_never_claims_global_or_live_authority():
    check = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage79_local_sqlite_cas_smoke.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert check.returncode == 0, check.stderr
    report = json.loads(check.stdout)
    assert report["mode"] == "STAGE79_OPTIONAL_SINGLE_DB_CAS_RESEARCH"
    assert report["sqlite_head_CAS_available"] is True
    assert report["global_mandatory_fo_risk_gateway"] is False
    assert report["legacy_direct_writes_blocked"] is False
    assert report["live_trading_enabled"] is False
    assert report["broker_orders_transmitted"] == 0
    assert report["verdict"].endswith("NO_GO")
