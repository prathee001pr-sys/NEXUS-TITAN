"""Stage83 one-file multi-F&O virtual account economics and NO-GO QA."""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOPortfolioRiskReview, Stage76UnderlyingExposure,
)
from nexus_titan.operations.stage83_fo_capital_reconciliation import (
    Stage83LedgerMismatch, inspect_stage83_fo_account_reconciliation,
)

CAP = 1_000_000


def b(path):
    return Stage55IsolatedSyntheticExecutionBook(
        db_path=path, account_id="qa-stage83", starting_cents=CAP,
        policy=Stage55SyntheticPolicy(),
    )


def research(*, account="qa-stage83", capital=CAP, nifty=150000, bank=150000):
    groups=(
        Stage76UnderlyingExposure("NIFTY",1,nifty,10000,1500),
        Stage76UnderlyingExposure("BANKNIFTY",1,bank,10000,1500),
    )
    return Stage76FOPortfolioRiskReview(
        account_id=account, virtual_capital_cents=capital,
        research_idea_count=2,total_hypothetical_debit_cents=nifty+bank,
        total_hypothetical_stress_loss_cents=20000,
        max_theoretical_premium_loss_cents=nifty+bank,
        total_debit_allocation_bps_rounded_up=3000,
        total_stress_loss_bps_rounded_up=200,
        underlying_exposures=groups,local_portfolio_budget_checks_passed=True,
        local_untrusted_risk_telemetry_checks_passed=True,
        local_research_fence_passed=True,
        input_packet_sha256=("a"*64,"b"*64),
        local_research_audit_sha256="c"*64,blockers=("NO_REAL_SOURCE",),
    )


def reserve(book, *, rid, symbol, amount):
    return book.reserve_synthetic_buy(
        request_id=rid,symbol=symbol,quantity=10,
        limit_price_cents=amount//10,fee_buffer_cents=0,
    )


def test_two_underlyings_one_sqlite_reserved_cash_reconciles(tmp_path):
    x=b(tmp_path/"single.db")
    reserve(x,rid="nifty",symbol="NIFTYOPT",amount=100000)
    reserve(x,rid="bank",symbol="BANKNIFTYOPT",amount=100000)
    s=x.snapshot_local_synthetic_portfolio()
    assert s.local_integrity_verified
    assert s.reserved_cents==200000
    assert s.available_cents==800000
    assert len(s.orders)==2
    report=inspect_stage83_fo_account_reconciliation(x,research())
    assert report.local_single_book_reconciliation_consistent
    assert report.local_budget_screen_passed
    assert report.simulated_committed_cents==200000
    assert {m.underlying:m.reserved_cents for m in report.markets}=={
        "NIFTY":100000,"BANKNIFTY":100000,
    }
    assert report.verdict.endswith("NO_GO")
    assert not report.global_single_atomic_capital_authority
    assert not report.paper_order_authorized and not report.live_trading_enabled
    assert report.broker_orders_transmitted==0
    assert inspect_stage83_fo_account_reconciliation(x,research())==report


def test_fill_then_cancel_reconciles_fees_and_commitment(tmp_path):
    x=b(tmp_path/"single.db")
    reserve(x,rid="nifty",symbol="NIFTYOPT",amount=100000)
    reserve(x,rid="bank",symbol="BANKNIFTYOPT",amount=100000)
    x.record_simulated_fill(
        order_id="nifty",fill_id="fill-nifty",quantity=10,
        price_cents=9500,fee_cents=0,
        evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
    )
    report=inspect_stage83_fo_account_reconciliation(x,research())
    assert report.simulated_reserved_cents==100000
    assert report.simulated_notional_paid_cents==95000
    assert report.simulated_committed_cents==195000
    x.cancel_unfilled(order_id="bank",cancel_id="cancel-bank",
                      evidence_source="LOCAL_SYNTHETIC_TEST_ONLY")
    last=inspect_stage83_fo_account_reconciliation(x,research())
    assert last.simulated_reserved_cents==0
    assert last.simulated_committed_cents==95000
    assert last.local_budget_screen_passed


def test_local_kill_switch_yields_reconciled_but_not_admissible(tmp_path):
    x=b(tmp_path/"single.db")
    reserve(x,rid="nifty",symbol="NIFTYOPT",amount=100000)
    x.set_local_synthetic_kill_switch(active=True,operation_id="stop")
    report=inspect_stage83_fo_account_reconciliation(x,research())
    assert report.local_single_book_reconciliation_consistent
    assert not report.local_budget_screen_passed
    assert report.local_kill_switch_active
    assert "LOCAL_BUDGET_OR_KILL_SWITCH_SCREEN_BLOCKED" in report.blockers


def test_unplanned_synthetic_symbol_does_not_get_paper_approval(tmp_path):
    x=b(tmp_path/"single.db")
    reserve(x,rid="other",symbol="FAKEOPT",amount=100000)
    with pytest.raises(Stage83LedgerMismatch,match="Unplanned instrument"):
        inspect_stage83_fo_account_reconciliation(x,research())


def test_stale_or_mismatched_account_balance_blocks(tmp_path):
    x=b(tmp_path/"single.db")
    for changed in (research(account="other"),research(capital=500000)):
        with pytest.raises(Stage83LedgerMismatch,match="account or virtual capital"):
            inspect_stage83_fo_account_reconciliation(x,changed)


def test_overbudget_stress_allocator_blocks_new_local_research(tmp_path):
    x=b(tmp_path/"single.db")
    reserve(x,rid="nifty",symbol="NIFTYOPT",amount=150000)
    reserve(x,rid="bank",symbol="BANKNIFTYOPT",amount=150000)
    report=inspect_stage83_fo_account_reconciliation(x,research(nifty=100000,bank=100000))
    assert not report.local_budget_screen_passed
    assert report.simulated_committed_cents==300000
    assert report.planned_hypothetical_debit_cents==200000


def test_tampered_sqlite_journal_rejected(tmp_path):
    path=tmp_path/"single.db"
    x=b(path)
    reserve(x,rid="nifty",symbol="NIFTYOPT",amount=100000)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE execution_head SET reserved_cents=1")
    with pytest.raises(Stage83LedgerMismatch,match="replay"):
        inspect_stage83_fo_account_reconciliation(x,research())


def test_separate_db_capital_double_claim_is_explicitly_unresolved(tmp_path):
    a=b(tmp_path/"a.db")
    other=b(tmp_path/"b.db")
    reserve(a,rid="nifty",symbol="NIFTYOPT",amount=100000)
    reserve(other,rid="bank",symbol="BANKNIFTYOPT",amount=100000)
    assert inspect_stage83_fo_account_reconciliation(a,research()).local_budget_screen_passed
    assert inspect_stage83_fo_account_reconciliation(other,research()).local_budget_screen_passed
    # Both books independently claim same CAP. This is intentionally not global.


def test_forged_stage76_approval_is_denied(tmp_path):
    x=b(tmp_path/"single.db")
    r=replace(research(),live_trading_enabled=True)
    with pytest.raises(Stage83LedgerMismatch,match="boundary"):
        inspect_stage83_fo_account_reconciliation(x,r)


@pytest.mark.parametrize("bad", [True,-1,0,1.5])
def test_invalid_stage76_budget_rejected(tmp_path,bad):
    x=b(tmp_path/"single.db")
    r=replace(research(),total_hypothetical_debit_cents=bad)
    with pytest.raises(Stage83LedgerMismatch):
        inspect_stage83_fo_account_reconciliation(x,r)
