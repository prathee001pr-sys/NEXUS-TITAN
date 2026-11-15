from dataclasses import replace
import pytest

from nexus_titan.operations.stage96_accounting_review import FOAccountingReview
from nexus_titan.operations.stage99_expiry_margin_review import Stage99SyntheticCase, review_synthetic_batch
from nexus_titan.operations.stage100_fo_reconciliation_gate import (
    Stage100Blocked, reconcile_fo_with_expiry_scenarios,
)


def valid_account(**changes):
    base = dict(market="INDIAN_FO", currency="INR", account_id="fo-test-1",
                journal_revision=3, journal_sha256="a" * 64, initial_cents=1000000,
                cash_cents=900000, remaining_cost_basis_cents=100000,
                realized_gross_pnl_cents=0, realized_net_pnl_cents=0,
                total_paid_execution_fees_cents=200, unrealized_net_pnl_cents=None,
                synthetic_equity_cents=None, position_count=1, closed_position_count=0,
                net_pnl_cents=None)
    base.update(changes)
    return FOAccountingReview(**base)


def scenario(**changes):
    kwargs = dict(contract_id="NIFTY-2026-11-12-CE-25000", underlying="NIFTY",
                  instrument_type="OPTIONS_LONG", expiry_date="2026-11-12",
                  settlement_timestamp="2026-11-12T15:31:00+05:30",
                  quote_source="SYNTHETIC_TEST_FIXTURE", quantity=75, lot_size=25,
                  settlement_spot=25050., entry_price=10., position_side="LONG",
                  option_type="CE", strike=25000.)
    kwargs.update(changes)
    return Stage99SyntheticCase(**kwargs)


def valid_batch():
    return review_synthetic_batch([scenario()])


def test_valid_account_keeps_expiry_unlinked():
    x = reconcile_fo_with_expiry_scenarios(valid_account(), valid_batch())
    assert x.account_id == "fo-test-1"
    assert x.scenario_count == 1
    assert len(x.scenario_sha256) == 64
    assert x.synthetic_equity_cents is None
    assert x.open_valuation_available is False
    assert x.expiry_to_journal_linkage_verified is False
    assert x.official_margin_verified is False
    assert x.executable is False and x.live_trading_enabled is False


def test_deterministic_scenario_digest():
    a = reconcile_fo_with_expiry_scenarios(valid_account(), valid_batch())
    b = reconcile_fo_with_expiry_scenarios(valid_account(), valid_batch())
    assert a == b
    assert a.scenario_sha256 != a.journal_sha256


def test_with_verified_synthetic_mark_stays_no_go():
    x = reconcile_fo_with_expiry_scenarios(
        valid_account(unrealized_net_pnl_cents=2000, synthetic_equity_cents=1002000,
                      net_pnl_cents=2000), valid_batch())
    assert x.open_valuation_available
    assert not x.expiry_to_journal_linkage_verified


@pytest.mark.parametrize("changes", [
    dict(market="CRYPTO_PAPER"), dict(currency="USDT"),
    dict(live_trading_enabled=True), dict(market_evidence_verified=True),
    dict(broker_orders_transmitted=1), dict(broker_orders_transmitted=True),
    dict(account_id=""), dict(account_id="../bad"),
    dict(journal_sha256="x" * 64), dict(journal_revision=-1),
    dict(initial_cents=-1), dict(cash_cents=-1),
    dict(cash_cents=900001), dict(remaining_cost_basis_cents=-1),
    dict(total_paid_execution_fees_cents=-3), dict(position_count=-1),
    dict(position_count=0), dict(profit_factor=5.0), dict(expectancy_cents=100.0),
    dict(max_drawdown_percent=0.3), dict(realized_net_pnl_cents=4),
    dict(unrealized_net_pnl_cents=50),
    dict(unrealized_net_pnl_cents=None, synthetic_equity_cents=1000000),
    dict(unrealized_net_pnl_cents=50, synthetic_equity_cents=1000050, net_pnl_cents=49),
    dict(unrealized_net_pnl_cents=50, synthetic_equity_cents=1, net_pnl_cents=50),
])
def test_account_boundaries_fail_closed(changes):
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios(valid_account(**changes), valid_batch())


@pytest.mark.parametrize("changes", [
    dict(currency="USDT"), dict(actual_settlement_verified=True),
    dict(authentic_margin_verified=True), dict(combined_live_execution_authorized=True),
    dict(combined_realized_pnl=100), dict(count=2), dict(cases=()),
    dict(verdict="READY_TO_TRADE"),
])
def test_batch_metadata_rejected(changes):
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios(valid_account(), replace(valid_batch(), **changes))


@pytest.mark.parametrize("changes", [
    dict(currency="USDT"), dict(live_trading_enabled=True),
    dict(exchange_settlement_verified=True), dict(official_margin_verified=True),
    dict(actual_broker_reconciled=True), dict(can_promote_or_execute=True),
    dict(synthetic_net_pnl=float("nan")), dict(indicative_margin_blocked=float("inf")),
    dict(lots=0), dict(contract_id="../bad"), dict(verdict="LIVE"),
])
def test_batch_case_tampering_rejected(changes):
    b = valid_batch()
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios(valid_account(), replace(b, cases=(replace(b.cases[0], **changes),)))


def test_duplicate_synthetic_case_rejected():
    b = valid_batch()
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios(valid_account(), replace(b, cases=(b.cases[0], b.cases[0]), count=2))


def test_wrong_input_types_rejected():
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios({}, valid_batch())
    with pytest.raises(Stage100Blocked):
        reconcile_fo_with_expiry_scenarios(valid_account(), {})
