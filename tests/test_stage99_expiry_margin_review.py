"""Synthetic-only negative gates and settlement/margin preflight tests."""
from dataclasses import replace
import pytest
from nexus_titan.operations.stage99_expiry_margin_review import (
    Stage99Blocked, Stage99SyntheticCase, review_synthetic_expiry_margin, review_dict, review_synthetic_batch,
)


def option(**updates):
    base = dict(contract_id="NIFTY-2026-11-12-CE-25000", underlying="NIFTY",
                instrument_type="OPTIONS_LONG", expiry_date="2026-11-12",
                settlement_timestamp="2026-11-12T15:31:00+05:30",
                quote_source="SYNTHETIC_TEST_FIXTURE", quantity=75, lot_size=25,
                settlement_spot=25050.0, entry_price=10.0, position_side="LONG",
                option_type="CE", strike=25000.0)
    base.update(updates)
    return Stage99SyntheticCase(**base)


def test_itm_call_review_is_unverified_and_brokerless():
    r=review_synthetic_expiry_margin(option())
    assert r.settlement_mode=="CASH_INDEX"
    assert r.lots==3
    assert r.synthetic_gross_pnl==3000
    assert r.synthetic_net_pnl < r.synthetic_gross_pnl
    assert r.official_margin_verified is False
    assert r.exchange_settlement_verified is False
    assert r.actual_broker_reconciled is False
    assert r.can_promote_or_execute is False
    assert r.live_trading_enabled is False


def test_put_itm_and_otm():
    a=review_synthetic_expiry_margin(option(option_type="PE",contract_id="NIFTY-2026-11-12-PE-25000", settlement_spot=24900))
    assert a.is_exercised is True
    b=review_synthetic_expiry_margin(option(settlement_spot=24900))
    assert b.is_exercised is False and b.settlement_mode=="EXPIRED_WORTHLESS"


def test_short_option_keeps_indicative_margin():
    r=review_synthetic_expiry_margin(option(instrument_type="OPTIONS_SHORT",position_side="SHORT"))
    assert r.synthetic_gross_pnl==-3000
    assert r.indicative_margin_blocked>0


def test_futures_long_short_and_net_pnl_no_go():
    kwargs=dict(contract_id="BANKNIFTY-2026-11-12-FUT",underlying="BANKNIFTY",
                instrument_type="FUTURES",option_type=None,strike=None,entry_price=56000,
                settlement_spot=56100,quantity=30,lot_size=15)
    a=review_synthetic_expiry_margin(option(**kwargs))
    b=review_synthetic_expiry_margin(option(**(kwargs | dict(position_side="SHORT"))))
    assert a.synthetic_gross_pnl==3000 and b.synthetic_gross_pnl==-3000
    assert a.synthetic_net_pnl is None and b.synthetic_net_pnl is None
    assert a.indicative_margin_blocked>0


@pytest.mark.parametrize('changes',[
    dict(live_trading_enabled=True),dict(source_currency="USDT"),
    dict(quote_source="NSE_VERIFIED"),dict(quote_source=""),
    dict(underlying="ETH"),dict(is_index_derivative=False),
    dict(contract_id="BANKNIFTY-MISMATCH"),dict(contract_id=""),
    dict(instrument_type="STOCK"),dict(position_side="BUY"),
    dict(quantity=0),dict(quantity=True),dict(quantity=26),dict(quantity=1000001),
    dict(lot_size=0),dict(lot_size=True),dict(lot_size=10001),
    dict(settlement_spot=float('nan')),dict(settlement_spot=float('inf')),
    dict(entry_price=-1),dict(entry_price=0),dict(entry_price=float('nan')),
    dict(expiry_date="2026-11-32"),dict(settlement_timestamp="bad-time"),
    dict(settlement_timestamp="2026-11-12T15:31:00"),
    dict(settlement_timestamp="2026-11-12T10:01:00Z"),
    dict(settlement_timestamp="2026-11-11T15:31:00+05:30"),
    dict(settlement_timestamp="2026-11-12T15:29:59+05:30"),
    dict(option_type="PE",contract_id="NIFTY-2026-11-12-CE-25000",strike=0),
    dict(option_type="OTHER"),dict(strike=None),dict(strike=float('nan')),
    dict(option_type="PE"),dict(strike=24900.0),dict(expiry_date="2026-11-13"),
    dict(instrument_type="OPTIONS_SHORT",position_side="LONG"),
    dict(instrument_type="OPTIONS_LONG",position_side="SHORT"),
    dict(instrument_type="FUTURES",strike=25000),
    dict(instrument_type="FUTURES",option_type="CE"),
])
def test_fail_closed(changes):
    with pytest.raises(Stage99Blocked):
        review_synthetic_expiry_margin(option(**changes))


def test_invalid_object_and_dict_export():
    with pytest.raises(Stage99Blocked): review_synthetic_expiry_margin(None)
    obj=review_dict(option())
    assert obj['verdict']=='SYNTHETIC_PREVIEW_ONLY_NO_GO' and obj['currency']=='INR'
    assert obj['can_promote_or_execute'] is False


@pytest.mark.parametrize('changes', [
    dict(settlement_spot=True),
    dict(settlement_spot=-1),
    dict(settlement_spot=1e9),
    dict(entry_price=True),
    dict(entry_price=1e9),
    dict(entry_price=float('-inf')),
    dict(quantity=-2),
    dict(quantity=1.5),
    dict(lot_size=-25),
    dict(lot_size=12.5),
    dict(settlement_timestamp='2026-11-12T15:31:00+05:45'),
    dict(settlement_timestamp='2026-11-12T23:59:59+00:00'),
    dict(settlement_timestamp='2026-11-12T15:29:59+05:30'),
    dict(settlement_timestamp='2026-11-13T15:31:00+05:30'),
    dict(is_index_derivative='yes'),
    dict(contract_id=123),
    dict(source_currency='INR;USDT'),
    dict(contract_id='NIFTY-2026-11-12-CE-25000-EXTRA'),
])
def test_additional_fail_closed_boundaries(changes):
    with pytest.raises(Stage99Blocked):
        review_synthetic_expiry_margin(option(**changes))


def test_atm_expires_without_exercise():
    r = review_synthetic_expiry_margin(option(settlement_spot=25000.0))
    assert r.settlement_mode == 'EXPIRED_WORTHLESS'
    assert r.is_exercised is False
    assert r.synthetic_gross_pnl == -750.0
    assert r.can_promote_or_execute is False


def test_valid_exact_close_timestamp_is_synthetic_only():
    r = review_synthetic_expiry_margin(option(settlement_timestamp='2026-11-12T15:30:00+05:30'))
    assert r.verdict == 'SYNTHETIC_PREVIEW_ONLY_NO_GO'
    assert r.exchange_settlement_verified is False


def test_immutable_result_and_no_live_authority():
    from dataclasses import FrozenInstanceError
    r = review_synthetic_expiry_margin(option())
    with pytest.raises(FrozenInstanceError):
        r.can_promote_or_execute = True
    assert r.actual_broker_reconciled is False


def test_quantity_lots_calculation_consistency():
    for qty in (25, 50, 100, 250):
        r = review_synthetic_expiry_margin(option(quantity=qty))
        assert r.lots * 25 == qty
        assert r.synthetic_gross_pnl == qty * (50 - 10)


@pytest.mark.parametrize("changes", [
    dict(quantity=1000000, lot_size=25),
    dict(quantity=100000, lot_size=25, settlement_spot=20000.0),
    dict(quantity=50000, lot_size=25, entry_price=50000.0),
    dict(quantity=50000, lot_size=25, strike=60000.0,
         contract_id="NIFTY-2026-11-12-CE-60000"),
])
def test_bounded_notional_rejects_float_large_exposure(changes):
    with pytest.raises(Stage99Blocked, match="notional"):
        review_synthetic_expiry_margin(option(**changes))


@pytest.mark.parametrize("kwargs", [
    dict(option_type="PE", contract_id="NIFTY-2026-11-12-PE-25000", settlement_spot=24900.0),
    dict(option_type="PE", contract_id="NIFTY-2026-11-12-PE-25000", settlement_spot=25050.0),
    dict(option_type="CE", contract_id="NIFTY-2026-11-12-CE-25000", settlement_spot=24950.0),
    dict(option_type="CE", contract_id="NIFTY-2026-11-12-CE-25000", settlement_spot=25000.0),
    dict(option_type="CE", contract_id="NIFTY-2026-11-12-CE-25000", settlement_spot=25100.0),
])
def test_payoff_scenarios_are_only_synthetic(kwargs):
    r = review_synthetic_expiry_margin(option(**kwargs))
    assert r.currency == "INR" and r.market == "INDIAN_FO"
    assert r.can_promote_or_execute is False
    assert r.exchange_settlement_verified is False
    assert r.actual_broker_reconciled is False
    assert r.official_margin_verified is False
    assert r.live_trading_enabled is False


@pytest.mark.parametrize("position_side", ["LONG", "SHORT"])
@pytest.mark.parametrize("option_type", ["CE", "PE"])
@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_synthetic_option_matrix(underlying, option_type, position_side):
    strike = 25000 if underlying == "NIFTY" else 50000
    case = option(
        contract_id=f"{underlying}-2026-11-12-{option_type}-{strike}",
        underlying=underlying,
        option_type=option_type,
        strike=float(strike),
        settlement_spot=float(strike + 50),
        position_side=position_side,
        instrument_type="OPTIONS_SHORT" if position_side == "SHORT" else "OPTIONS_LONG",
    )
    r = review_synthetic_expiry_margin(case)
    assert r.verdict == "SYNTHETIC_PREVIEW_ONLY_NO_GO"
    assert r.synthetic_net_pnl is not None
    assert r.lots == 3


def test_batch_two_underlyings_keeps_one_currency_and_no_aggregate_pnl():
    a = option()
    b = option(underlying="BANKNIFTY", contract_id="BANKNIFTY-2026-11-12-FUT",
               instrument_type="FUTURES", option_type=None, strike=None,
               settlement_spot=50000.0, entry_price=49900.0,
               quantity=30, lot_size=15)
    r = review_synthetic_batch([a, b])
    assert r.count == 2
    assert len(r.cases) == 2
    assert r.cases[0].market == r.cases[1].market == r.market == "INDIAN_FO"
    assert r.currency == "INR" and r.combined_realized_pnl is None
    assert r.authentic_margin_verified is False
    assert r.actual_settlement_verified is False
    assert r.combined_live_execution_authorized is False
    assert r.verdict.endswith("NO_GO")


@pytest.mark.parametrize("cases", [
    [], (), None, "not-a-sequence", (option(), option()),
    [option(), "untrusted"],
    [option(), option(live_trading_enabled=True,
                     contract_id="NIFTY-2026-11-12-PE-25000", option_type="PE")],
    [option(), option(source_currency="USDT",
                     contract_id="NIFTY-2026-11-12-PE-25000", option_type="PE")],
])
def test_batch_fails_closed_for_duplicate_untrusted_or_unsafe(cases):
    with pytest.raises(Stage99Blocked):
        review_synthetic_batch(cases)


def test_batch_rejects_oversized_before_iterating_cases():
    with pytest.raises(Stage99Blocked):
        review_synthetic_batch([option()] * 51)


def test_batch_immutable_result_even_if_input_list_mutates():
    inputs = [option()]
    result = review_synthetic_batch(inputs)
    inputs.clear()
    assert result.count == 1 and len(result.cases) == 1
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        result.combined_live_execution_authorized = True


def test_unknown_underlying_does_not_reach_legacy_helpers(monkeypatch):
    import nexus_titan.operations.stage99_expiry_margin_review as mod
    def forbidden(**kwargs):
        raise AssertionError("Legacy derivative helper should not be called")
    monkeypatch.setattr(mod, "settle_option_at_expiry", forbidden)
    monkeypatch.setattr(mod, "estimate_span_elm_margin", forbidden)
    with pytest.raises(Stage99Blocked):
        review_synthetic_expiry_margin(option(underlying="BTC"))


def test_futures_source_entirely_readonly(monkeypatch):
    import nexus_titan.operations.stage99_expiry_margin_review as mod
    seen = []
    legacy = mod.estimate_span_elm_margin
    def wrapper(**kwargs):
        seen.append(kwargs.copy())
        return legacy(**kwargs)
    monkeypatch.setattr(mod, "estimate_span_elm_margin", wrapper)
    r = review_synthetic_expiry_margin(option(contract_id="NIFTY-2026-11-12-FUT",
         instrument_type="FUTURES", option_type=None, strike=None,
         entry_price=25000.0))
    assert r.synthetic_net_pnl is None
    assert seen and seen[0]["instrument_type"] == "FUTURES"
    assert r.can_promote_or_execute is False


@pytest.mark.parametrize("value", [[option(contract_id=["NIFTY"])],
                                  [option(contract_id={"NIFTY": 1})]])
def test_batch_unhashable_contract_id_is_cleanly_blocked(value):
    with pytest.raises(Stage99Blocked):
        review_synthetic_batch(value)


def test_subclass_input_cannot_override_verified_case_accessors():
    class UntrustedSubclass(Stage99SyntheticCase):
        pass
    with pytest.raises(Stage99Blocked):
        review_synthetic_expiry_margin(UntrustedSubclass(**{f: getattr(option(), f) for f in option().__dataclass_fields__}))


def test_untrusted_list_subclass_rejected_before_iteration():
    class PoisonList(list):
        def __iter__(self):
            raise AssertionError("Must not iterate custom collection")
    with pytest.raises(Stage99Blocked):
        review_synthetic_batch(PoisonList([option()]))
