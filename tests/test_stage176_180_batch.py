"""Read-only deterministic regression for Stages 176–180."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.stage167_execution_fill_bounds import FillReceipt
from nexus_titan.data.stage173_settlement_ledger import SettlementReceipt
from nexus_titan.data.stage175_offline_review_gate import OfflineReviewReceipt
from nexus_titan.data.stage176_quote_sanity import audit_quote, QuoteReceipt
from nexus_titan.data.stage177_liquidity_participation import audit_liquidity_fill
from nexus_titan.data.stage178_portfolio_risk_budget import audit_portfolio_risk
from nexus_titan.data.stage179_closed_trade_scorecard import audit_closed_trade_scorecard
from nexus_titan.data.stage180_paper_evidence_gate import evaluate_paper_evidence

T = datetime(2026, 11, 12, 9, 15, tzinfo=timezone.utc)
DIGEST = 'a' * 64


def quote(**changes):
    args = dict(bid='100', ask='102', tick_size='1', quote_at=T,
                decision_at=T + timedelta(milliseconds=150),
                max_quote_age_ms=500, max_spread_bps=300)
    args.update(changes)
    return audit_quote(**args)


def liquidity(**changes):
    args = dict(side='BUY', fill_price='102.50', bid='100', ask='102',
                filled_units='5', observed_bar_units='1000',
                max_participation_bps=100, max_quote_slippage_bps=100,
                units_verified=True, quote=quote(), fill=FillReceipt(True, ()))
    args.update(changes)
    return audit_liquidity_fill(**args)


def risk(**changes):
    args = dict(equity='10000', position_notional='30000',
                initial_margin='4000', risk_at_stop='100',
                max_leverage=3, max_risk_bps=100,
                margin_verified=True, stop_model_verified=True)
    args.update(changes)
    return audit_portfolio_risk(**args)


def trades():
    return (SettlementReceipt(True, Decimal('10'), Decimal('8'), ()),
            SettlementReceipt(True, Decimal('-5'), Decimal('-6'), ()))


def scorecard(**changes):
    args = dict(opening_equity='10000', max_drawdown_bps=100, min_trades=2)
    args.update(changes)
    return audit_closed_trade_scorecard(trades(), **args)


def paper(**changes):
    args = dict(prior=OfflineReviewReceipt(True, (), False), quote=quote(),
                liquidity=liquidity(), risk=risk(), scorecard=scorecard(),
                dataset_sha256=DIGEST, verified_snapshot_sha256=DIGEST,
                cost_assumptions_verified=True)
    args.update(changes)
    return evaluate_paper_evidence(**args)


def test_176_valid_quote():
    r = quote()
    assert r.accepted and r.midpoint == Decimal('101')
    assert r.spread_bps > 0


def test_176_boundary_limits_are_inclusive():
    r = quote(bid='100', ask='100', quote_at=T, decision_at=T,
              max_spread_bps=0, max_quote_age_ms=0)
    assert r.accepted and r.spread_bps == 0


@pytest.mark.parametrize('changes,blocker', [
    ({'bid':'103'}, 'crossed quote'),
    ({'bid':'100.1'}, 'off-tick'),
    ({'max_spread_bps':10}, 'spread exceeds'),
    ({'decision_at':T + timedelta(seconds=2)}, 'stale quote'),
    ({'quote_at':T + timedelta(seconds=2)}, 'future quote'),
    ({'quote_at':T.replace(tzinfo=None)}, 'aware timestamps'),
    ({'tick_size':'0'}, 'nonpositive'),
    ({'bid':100.0}, 'invalid quote amounts'),
    ({'bid':'NaN'}, 'invalid quote amounts'),
    ({'max_quote_age_ms':True}, 'invalid limits'),
    ({'max_spread_bps':-1}, 'invalid limits'),
])
def test_176_fail_closed(changes, blocker):
    r = quote(**changes)
    assert not r.accepted and blocker in ' '.join(r.blockers)


def test_177_liquidity_good():
    r = liquidity()
    assert r.accepted and r.participation_bps == Decimal('50')


@pytest.mark.parametrize('changes,blocker', [
    ({'observed_bar_units':'100'}, 'excessive market participation'),
    ({'units_verified':False}, 'unverified comparable units'),
    ({'quote':QuoteReceipt(False,None,None,('fail',))}, 'quote audit required'),
    ({'fill':FillReceipt(False,('fail',))}, 'fill audit required'),
    ({'fill_price':'110'}, 'fill outside quote tolerance'),
    ({'fill_price':'99'}, 'fill outside quote tolerance'),
    ({'observed_bar_units':'0'}, 'invalid price or volume'),
    ({'side':'HOLD'}, 'invalid side'),
    ({'max_participation_bps':True}, 'invalid limits'),
    ({'max_quote_slippage_bps':-1}, 'invalid limits'),
])
def test_177_fail_closed(changes, blocker):
    r = liquidity(**changes)
    assert not r.accepted and blocker in ' '.join(r.blockers)


def test_177_sell_at_bid():
    assert liquidity(side='SELL',fill_price='100').accepted


def test_178_good_risk_budget():
    r = risk()
    assert r.accepted and r.risk_bps == Decimal('100')


@pytest.mark.parametrize('changes,blocker', [
    ({'initial_margin':'11000'}, 'insufficient capital'),
    ({'position_notional':'30001'}, 'notional exceeds'),
    ({'risk_at_stop':'100.01'}, 'stop risk exceeds'),
    ({'margin_verified':False}, 'margin assumptions'),
    ({'stop_model_verified':False}, 'stop model'),
    ({'equity':'0'}, 'invalid equity'),
    ({'equity':10000.0}, 'invalid numeric'),
    ({'max_leverage':True}, 'invalid leverage'),
    ({'max_risk_bps':0}, 'invalid stop risk'),
])
def test_178_fail_closed(changes, blocker):
    r = risk(**changes)
    assert not r.accepted and blocker in ' '.join(r.blockers)


def test_179_closed_trades_metrics():
    r = scorecard()
    assert r.accepted and r.net_pnl == Decimal('2')
    assert r.profit_factor == Decimal(8) / Decimal(6)
    assert r.expectancy == Decimal(1)
    assert Decimal(0) < r.max_drawdown_bps < Decimal(7)


def test_179_zero_loss_profit_factor_undefined_not_infinity():
    r = audit_closed_trade_scorecard((trades()[0],), opening_equity='100',
                                     max_drawdown_bps=100, min_trades=1)
    assert r.accepted and r.profit_factor is None


def test_179_reject_equity_depleted():
    r = audit_closed_trade_scorecard((SettlementReceipt(True, Decimal('-1000'),
        Decimal('-1000'), ()),), opening_equity='100', max_drawdown_bps=10000)
    assert not r.accepted and r.net_pnl is None


@pytest.mark.parametrize('changes,blocker', [
    ({'opening_equity':'0'}, 'invalid opening equity'),
    ({'max_drawdown_bps':1}, 'drawdown limit breached'),
    ({'min_trades':3}, 'insufficient closed trades'),
    ({'min_trades':True}, 'invalid minimum trade'),
    ({'max_drawdown_bps':True}, 'invalid drawdown'),
])
def test_179_fail_closed(changes, blocker):
    r = scorecard(**changes)
    assert not r.accepted and blocker in ' '.join(r.blockers)


def test_179_invalid_unverified_trade_and_empty_list():
    bad = SettlementReceipt(False, None, None, ('fail',))
    assert not audit_closed_trade_scorecard((bad,), opening_equity='100',max_drawdown_bps=100).accepted
    assert not audit_closed_trade_scorecard((),opening_equity='100',max_drawdown_bps=100).accepted


def test_180_paper_gate_remains_offline_only():
    r = paper()
    assert r.accepted_for_offline_paper_review
    assert r.live_trading_authorized is False
    assert r.strategy_promotion_authorized is False


@pytest.mark.parametrize('changes,blocker', [
    ({'prior':True}, 'prior offline review'),
    ({'quote':quote(bid='103')}, 'quote sanity'),
    ({'liquidity':liquidity(units_verified=False)}, 'liquidity'),
    ({'risk':risk(margin_verified=False)}, 'portfolio risk'),
    ({'scorecard':scorecard(max_drawdown_bps=0)}, 'closed trade scorecard'),
    ({'dataset_sha256':'b'*64}, 'verified dataset digest'),
    ({'dataset_sha256':'ABC'}, 'verified dataset digest'),
    ({'cost_assumptions_verified':1}, 'calibrated cost assumptions'),
    ({'real_fill_claimed':True}, 'no real fill claim'),
    ({'live_requested':True}, 'live trading prohibited'),
    ({'promotion_requested':True}, 'promotion prohibited'),
])
def test_180_gate_fail_closed(changes, blocker):
    r = paper(**changes)
    assert not r.accepted_for_offline_paper_review
    assert blocker in r.blockers
    assert not r.live_trading_authorized and not r.strategy_promotion_authorized


def test_177_quote_provenance_values_must_match():
    r = liquidity(bid='99')
    assert not r.accepted and 'quote values differ from validated quote' in r.blockers


def test_177_reject_accepted_fill_with_errors():
    assert not liquidity(fill=FillReceipt(True, ('prior error',))).accepted


def test_179_reject_inconsistent_or_unbounded_settlement():
    malformed = SettlementReceipt(True, None, Decimal('1'), ())
    forged = SettlementReceipt(True, Decimal('1'), Decimal('1e30'), ())
    for row in (malformed, forged):
        result = audit_closed_trade_scorecard((row,), opening_equity='100', max_drawdown_bps=100)
        assert not result.accepted


def test_180_reject_accepted_receipt_with_blockers():
    q = quote()
    fake = QuoteReceipt(True, q.midpoint, q.spread_bps, ('unresolved',))
    assert not paper(quote=fake).accepted_for_offline_paper_review


def test_179_reject_net_pnl_exceeding_gross():
    fabricated = SettlementReceipt(True, Decimal('1'), Decimal('2'), ())
    result = audit_closed_trade_scorecard((fabricated,), opening_equity='100', max_drawdown_bps=100)
    assert not result.accepted
