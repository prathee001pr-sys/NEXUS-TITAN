from dataclasses import replace
import pytest

from nexus_titan.operations.stage96_accounting_review import FOAccountingReview
from nexus_titan.operations.stage98_dual_market_review import DualMarketReview
from nexus_titan.operations.stage99_expiry_margin_review import Stage99SyntheticCase, review_synthetic_batch
from nexus_titan.operations.stage100_fo_reconciliation_gate import reconcile_fo_with_expiry_scenarios
from nexus_titan.operations.stage101_historical_bar_preflight import Stage101SyntheticBar, review_stage101_synthetic_window
from nexus_titan.operations.stage102_option_chain_preflight import Stage102SyntheticQuote, review_stage102_synthetic_chain
from nexus_titan.operations.stage103_readonly_assurance_gate import (
    Stage103Blocked, verify_stage103_readonly_assurance,
)


def fixtures():
    account = FOAccountingReview(
        market="INDIAN_FO", currency="INR", account_id="account-100", journal_revision=7,
        journal_sha256="a" * 64, initial_cents=1000000, cash_cents=900000,
        remaining_cost_basis_cents=100000, realized_gross_pnl_cents=0,
        realized_net_pnl_cents=0, total_paid_execution_fees_cents=100,
        unrealized_net_pnl_cents=None, synthetic_equity_cents=None,
        position_count=1, closed_position_count=0, net_pnl_cents=None,
    )
    case = Stage99SyntheticCase(
        contract_id="NIFTY-2026-11-12-CE-25000", underlying="NIFTY",
        instrument_type="OPTIONS_LONG", expiry_date="2026-11-12",
        settlement_timestamp="2026-11-12T15:31:00+05:30",
        quote_source="SYNTHETIC_TEST_FIXTURE", quantity=75, lot_size=25,
        settlement_spot=25050., entry_price=10., position_side="LONG", option_type="CE", strike=25000.,
    )
    fo = reconcile_fo_with_expiry_scenarios(account, review_synthetic_batch([case]))
    bars = review_stage101_synthetic_window([Stage101SyntheticBar(
        "NIFTY", "2026-11-10T09:15:00+05:30", 2500000, 2500200, 2499900, 2500100, 100,
    )])
    quotes = [Stage102SyntheticQuote(
        f"NIFTY-2026-11-12-{kind}-2500000", "NIFTY", "2026-11-12",
        "2026-11-10T09:15:00+05:30", kind, 2500000, 1000, 1100, 100, 1, 25,
    ) for kind in ("CE", "PE")]
    chain = review_stage102_synthetic_chain(bars, quotes)
    dual = DualMarketReview(
        indian=dict(market="INDIAN_FO", currency="INR", account_id="account-100",
                    journal_sha256="a" * 64, journal_revision=7,
                    initial_cents=1000000, cash_cents=900000, remaining_cost_basis_cents=100000,
                    realized_net_pnl_cents=0, live_trading_enabled=False, market_evidence_verified=False,
                    broker_orders_transmitted=0),
        crypto=dict(market="CRYPTO_PAPER", currency="USDT", account_id="crypto-201",
                    journal_tip="b" * 64, initial_cents=1000000, cash_cents=950000,
                    remaining_cost_basis_cents=50000, realized_net_pnl_cents=0,
                    live_trading_enabled=False,
                    real_market_evidence_verified=False, exchange_orders_transmitted=0),
    )
    return fo, bars, chain, dual


def check(fo=None, bars=None, chain=None, dual=None):
    f, b, c, d = fixtures()
    return verify_stage103_readonly_assurance(
        f if fo is None else fo, b if bars is None else bars,
        c if chain is None else chain, d if dual is None else dual,
    )


def test_real_types_and_identical_fingerprint():
    x = check()
    y = check()
    assert x == y
    assert len(x.review_sha256) == 64
    assert x.indian_currency == "INR" and x.crypto_currency == "USDT"
    assert x.underlying == "NIFTY"
    assert x.synthetic_inputs_consistent is True
    assert x.trade_authorized is False and x.live_trading_enabled is False
    assert x.source_authenticity_verified is False
    assert x.expiry_to_account_linkage_verified is False
    assert x.real_market_shadow_verified is False


@pytest.mark.parametrize("changes", [
    dict(currency="USDT"), dict(live_trading_enabled=True), dict(executable=True),
    dict(expiry_to_journal_linkage_verified=True), dict(exchange_settlement_verified=True),
    dict(broker_contract_note_verified=True), dict(official_margin_verified=True),
    dict(journal_sha256="c" * 64), dict(journal_sha256="not-hash"),
    dict(journal_revision=-1), dict(scenario_count=0),
    dict(scenario_sha256="broken"), dict(scenario_instrument_ids=()),
    dict(scenario_instrument_ids=("BANKNIFTY-2026-11-12-FUT",)),
    dict(verdict="READY"),
])
def test_fo_tamper_detected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(replace(f, **changes), b, c, d)


@pytest.mark.parametrize("changes", [
    dict(symbol="BANKNIFTY"), dict(currency="USDT"), dict(timeframe="15m"),
    dict(contiguous_one_minute_bars=False), dict(verified_trading_calendar=True),
    dict(independent_market_source_verified=True), dict(fifteen_year_history_verified=True),
    dict(live_trading_enabled=True), dict(content_sha256="bad"),
    dict(verdict="READY"),
])
def test_bar_tamper_detected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, replace(b, **changes), c, d)


@pytest.mark.parametrize("changes", [
    dict(currency="USDT"), dict(underlying="BANKNIFTY"),
    dict(official_option_chain_verified=True),
    dict(official_expiry_calendar_verified=True),
    dict(executable_liquidity_verified=True),
    dict(broker_order_authorized=True), dict(live_trading_enabled=True),
    dict(structural_chain_valid=False),
    dict(source_window_sha256="c" * 64), dict(chain_sha256="garbled"),
    dict(quote_count=3), dict(paired_strike_count=0), dict(verdict="READY"),
    dict(expiry_date="2026-11-19"),
])
def test_chain_tamper_detected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, b, replace(c, **changes), d)


@pytest.mark.parametrize("changes", [
    dict(live_trading_enabled=True), dict(real_market_shadow_validated=True),
    dict(cross_currency_conversion_verified=True),
    dict(combined_pnl_cents=1), dict(combined_cash_cents=100),
    dict(verdict="READY"), dict(indian=[]), dict(crypto=[]),
])
def test_dual_tamper_detected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, b, c, replace(d, **changes))


@pytest.mark.parametrize("changes", [
    dict(account_id="other"), dict(currency="USDT"), dict(market="CRYPTO_PAPER"),
    dict(journal_sha256="c" * 64), dict(journal_revision=8),
    dict(live_trading_enabled=True), dict(market_evidence_verified=True),
    dict(broker_orders_transmitted=1), dict(cash_cents=1),
    dict(remaining_cost_basis_cents=1), dict(realized_net_pnl_cents=1),
])
def test_indian_account_mismatch_rejected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, b, c, replace(d, indian=d.indian | changes))


@pytest.mark.parametrize("changes", [
    dict(account_id="account-100"), dict(account_id="bad/path"),
    dict(currency="INR"), dict(market="INDIAN_FO"),
    dict(journal_tip="broken"), dict(live_trading_enabled=True),
    dict(real_market_evidence_verified=True), dict(exchange_orders_transmitted=1),
    dict(cash_cents=1), dict(initial_cents=1),
])
def test_crypto_isolation_mismatch_rejected(changes):
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, b, c, replace(d, crypto=d.crypto | changes))


def test_wrong_input_type_rejected():
    f, b, c, d = fixtures()
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance({}, b, c, d)
    with pytest.raises(Stage103Blocked):
        verify_stage103_readonly_assurance(f, b, c, {})


def test_report_is_frozen_and_never_trading_permit():
    x = check()
    with pytest.raises(Exception):
        x.trade_authorized = True
    assert not x.broker_fills_reconciled
