"""Stage19 synthetic-only durable research capital reservation regression tests."""
from dataclasses import replace
from datetime import date, datetime, timedelta
import hashlib
import sqlite3

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)
from nexus_titan.simulation.options_order_reconciliation import ResearchFillEvent
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)

OBS = datetime.fromisoformat("2026-11-02T09:16:00+05:30")


def _contract(**overrides):
    args = dict(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1000, max_lots_per_trade=10,
        strike_step=50.0, expiry_date=date(2026, 11, 5),
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        source_reference="research/contract-review", source_verified=True,
    )
    args.update(overrides)
    return PointInTimeContractSpec(**args)


def _history():
    ts = (OBS - timedelta(seconds=1)).isoformat()
    quotes = tuple(OptionChainQuote(
        timestamp=ts, symbol="NIFTYOPT", underlying="NIFTY",
        expiry_date="2026-11-05", strike=100.0, option_type=side,
        bid=5.0, ask=5.5, ltp=5.25, volume=1000, open_interest=1000,
        underlying_spot=100.0, lot_size=25,
    ) for side in ("CE", "PE"))
    item = ResearchOptionChainSnapshot(
        quotes=quotes, sha256=hashlib.sha256(b"synthetic only").hexdigest(),
        observed_at=OBS, provider_reference="research/provider",
        licence_evidence_reference="research/licence",
        calendar_evidence_reference="research/calendar",
        contract_evidence_reference="research/contract-review",
    )
    return assemble_research_option_chain_history(
        [item], contract=_contract(), calendar=nse_equity_derivatives_baseline(),
    )


def _fragment(*, lots=4, depth_ask=200):
    depth = OptionDisplayedDepth(
        as_of=OBS, bid_quantity=400, ask_quantity=depth_ask,
        source_reference="research/depth", source_declared_verified=True,
    )
    return simulate_historical_option_fill(
        _history(), contract=_contract(), calendar=nse_equity_derivatives_baseline(),
        observed_at=OBS, strike=100, option_type="CE", side="BUY",
        lots=lots, depth=depth,
    )


def _evt(event_id, fragment, time=OBS):
    return ResearchFillEvent(event_id=event_id, observed_at=time, fragment=fragment)


def _db(tmp_path, *, account_id="A", starting_capital=50000):
    return DurableResearchShadowLedger(
        tmp_path / "shadow.sqlite3", account_id=account_id, starting_capital=starting_capital,
    )


def _reserve(ledger, order="ONE", *, lots=4, premium=6.0, fee_buffer=25.0, **changes):
    args = dict(
        order_id=order, contract=_contract(), strike=100.0, option_type="CE",
        lots=lots, as_of=OBS, max_unit_premium=premium, fee_buffer=fee_buffer,
    )
    args.update(changes)
    ledger.reserve_buy(**args)


def _settle(ledger, order="ONE", events=None, **changes):
    if events is None:
        events=[_evt("FILL-1", _fragment())]
    args=dict(
        order_id=order, contract=_contract(), strike=100.0,
        option_type="CE", events=events,
    )
    args.update(changes)
    return ledger.settle_buy(**args)


def test_initial_status_configurable_capital_and_durable_genesis(tmp_path):
    ledger=_db(tmp_path, starting_capital=23000)
    s=ledger.status()
    assert s.starting_capital==23000 and s.cash_balance==23000
    assert s.reserved_cash==0 and s.available_cash==23000
    assert s.audit_event_count==1 and ledger.verify_integrity()
    assert s.live_orders_transmitted==0
    assert s.approved_for_strategy_promotion is False


def test_two_orders_reserve_against_shared_available_cash(tmp_path):
    ledger=_db(tmp_path, starting_capital=1000)
    _reserve(ledger, "ONE")
    _reserve(ledger, "TWO", lots=1)
    s=ledger.status()
    assert s.open_order_count==2
    assert s.reserved_cash==800.0 and s.available_cash==200.0
    with pytest.raises(ResearchLedgerError,match="Insufficient unreserved"):
        _reserve(ledger, "THREE", lots=2)
    assert ledger.status()==s


def test_cancel_releases_cash_restart_and_prevents_order_id_reuse(tmp_path):
    ledger=_db(tmp_path,starting_capital=1000)
    _reserve(ledger)
    assert ledger.status().reserved_cash==625
    ledger.cancel("ONE")
    assert ledger.status().available_cash==1000
    other=_db(tmp_path,starting_capital=1000)
    assert other.status().cancelled_order_count==1
    assert other.verify_integrity()
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed"):
        _reserve(other)
    with pytest.raises(ResearchLedgerError,match="Only OPEN"):
        other.cancel("ONE")


def test_single_partial_fill_is_terminal_releases_remaining_reservation(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    report=_settle(ledger)
    s=ledger.status()
    assert report.status=="PARTIAL" and report.filled_quantity==50
    assert s.closed_order_count==1 and s.open_order_count==0
    assert s.reserved_cash==0
    assert s.cash_balance==round(50000-report.filled_notional-report.conservative_fee_reserve,2)
    assert sum(qty for _,qty in s.option_inventory)==50
    assert report.live_orders_transmitted==0
    with pytest.raises(ResearchLedgerError,match="Only OPEN"):
        _settle(ledger)


def test_two_fragment_order_terminal_full_100_units(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    events=[
        _evt("A",_fragment()),
        _evt("B",_fragment(lots=2,depth_ask=400),OBS+timedelta(seconds=1)),
    ]
    report=_settle(ledger,events=events)
    assert report.filled_quantity==100 and report.status=="FILLED"
    assert sum(qty for _,qty in ledger.status().option_inventory)==100
    assert ledger.status().reserved_cash==0


def test_unfilled_order_closes_without_fake_cash_or_position(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    outcome=_settle(ledger,events=[_evt("NONE",_fragment(depth_ask=0))])
    assert outcome.status=="UNFILLED"
    s=ledger.status()
    assert s.cash_balance==50000 and s.reserved_cash==0
    assert s.option_inventory==() and s.closed_order_count==1


def test_replayed_fill_event_across_different_orders_and_restart_is_rejected(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger,"ONE",lots=1)
    _reserve(ledger,"TWO",lots=1)
    _settle(ledger,"ONE",events=[_evt("ID-1",_fragment(lots=1,depth_ask=400))])
    restarted=_db(tmp_path)
    before=restarted.status()
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed"):
        _settle(restarted,"TWO",events=[_evt("ID-1",_fragment(lots=1,depth_ask=400))])
    assert restarted.status()==before and restarted.status().open_order_count==1


def test_underreserved_fee_buffer_rolls_back_atomically(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger, premium=5.50, fee_buffer=0)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="exceeds reserved"):
        _settle(ledger,events=[_evt("OVER-RESERVE",_fragment(lots=4,depth_ask=400))])
    assert ledger.status()==before
    ledger.cancel("ONE")
    assert ledger.status().available_cash==50000


def test_bad_initial_capital_on_restart_is_blocked(tmp_path):
    _db(tmp_path,starting_capital=10000)
    with pytest.raises(ResearchLedgerError,match="differs"):
        _db(tmp_path,starting_capital=9999)


def test_independent_accounts_share_sqlite_without_sharing_cash(tmp_path):
    a=_db(tmp_path,account_id="A",starting_capital=1000)
    b=_db(tmp_path,account_id="B",starting_capital=2000)
    _reserve(a,"SAME",lots=1)
    _reserve(b,"SAME",lots=2)
    assert a.status().reserved_cash==175 and b.status().reserved_cash==325
    assert a.verify_integrity() and b.verify_integrity()


def test_tampered_cash_balance_is_detected_on_restart_and_mutations(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    with sqlite3.connect(tmp_path/"shadow.sqlite3") as c:
        c.execute("UPDATE accounts SET cash_cents=cash_cents+999 WHERE account_id='A'")
    with pytest.raises(ResearchLedgerError,match="state does not match"):
        ledger.status()
    with pytest.raises(ResearchLedgerError,match="state does not match"):
        _reserve(ledger,order="TWO")


def test_tampered_audit_record_is_detected(tmp_path):
    ledger=_db(tmp_path)
    with sqlite3.connect(tmp_path/"shadow.sqlite3") as c:
        c.execute("UPDATE audit SET payload_json='{}' WHERE account_id='A'")
    with pytest.raises(ResearchLedgerError,match="audit chain corrupted"):
        ledger.verify_integrity()


def test_reserved_money_is_not_debited_until_settlement(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    s=ledger.status()
    assert s.cash_balance==50000 and s.reserved_cash==625 and s.available_cash==49375


def test_wrong_contract_or_strike_cannot_settle_reservation(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    with pytest.raises(ResearchLedgerError,match="Contract/strike/side"):
        _settle(ledger,strike=150)
    with pytest.raises(ResearchLedgerError,match="Contract/strike/side"):
        _settle(ledger,contract=_contract(source_reference="other/review"))
    assert ledger.status().open_order_count==1


def test_mismatched_promotion_boundary_fragment_rejected(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    fragment=replace(_fragment(),live_orders_transmitted=1)
    with pytest.raises(ValueError,match="promotion/live"):
        _settle(ledger,events=[_evt("BAD",fragment)])
    assert ledger.status().reserved_cash==625


def test_historical_event_prior_to_reservation_fails(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    with pytest.raises(ResearchLedgerError,match="pre-reservation"):
        _settle(ledger,events=[_evt("EARLY",_fragment(),OBS-timedelta(seconds=1))])


def test_buy_budget_fails_on_small_virtual_capital(tmp_path):
    ledger=_db(tmp_path,starting_capital=200)
    with pytest.raises(ResearchLedgerError,match="Insufficient unreserved"):
        _reserve(ledger)
    assert ledger.status().open_order_count==0


def test_freeze_and_lot_ceiling_cannot_be_bypassed(tmp_path):
    ledger=_db(tmp_path)
    with pytest.raises(ResearchLedgerError,match="whole-lot"):
        _reserve(ledger,lots=11)
    with pytest.raises(ResearchLedgerError,match="freeze"):
        _reserve(ledger,contract=_contract(freeze_quantity=25),lots=2)


@pytest.mark.parametrize("bad", [0,-1,True,float("nan"),float("inf"),5.123])
def test_invalid_reserve_premium_rejected(tmp_path,bad):
    ledger=_db(tmp_path)
    with pytest.raises(ResearchLedgerError):
        _reserve(ledger,premium=bad)


@pytest.mark.parametrize("bad", [-1,True,float("nan"),5.001])
def test_invalid_fee_buffer_rejected(tmp_path,bad):
    ledger=_db(tmp_path)
    with pytest.raises(ResearchLedgerError):
        _reserve(ledger,fee_buffer=bad)


def test_max_premium_requires_exchange_tick_alignment(tmp_path):
    ledger=_db(tmp_path)
    with pytest.raises(ResearchLedgerError,match="contract tick"):
        _reserve(ledger,premium=6.01)


def test_duplicate_order_rejected_without_changing_reservations(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    previous=ledger.status()
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed"):
        _reserve(ledger)
    assert previous==ledger.status()


def test_empty_event_list_is_rejected(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    with pytest.raises(ResearchLedgerError,match="Non-empty"):
        _settle(ledger,events=[])


def test_source_unverified_contract_does_not_reserve(tmp_path):
    ledger=_db(tmp_path)
    with pytest.raises(ResearchLedgerError,match="reviewed source"):
        _reserve(ledger,contract=_contract(source_verified=False))


def test_zero_and_nonfinite_initial_cash_rejected(tmp_path):
    for bad in (0,-1,True,float("inf"),float("nan")):
        with pytest.raises(ResearchLedgerError):
            _db(tmp_path,account_id=f"A-{str(bad)}",starting_capital=bad)


def test_restart_retains_positions_cash_and_fill_replay(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    _settle(ledger,events=[_evt("SUCCESS",_fragment())])
    state=ledger.status()
    restored=_db(tmp_path)
    assert restored.status()==state
    assert restored.verify_integrity()


def test_no_broker_operations_emitted(tmp_path):
    ledger=_db(tmp_path)
    _reserve(ledger)
    _settle(ledger)
    assert ledger.status().live_orders_transmitted==0
    assert ledger.status().approved_for_strategy_promotion is False
