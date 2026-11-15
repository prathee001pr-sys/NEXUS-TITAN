"""Synthetic-only portfolio integration, negative controls and fail-closed gates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from nexus_titan.data.stage190_e2e_paper_replay import E2EPaperReplayReceipt, replay_synthetic_roundtrip
from nexus_titan.data.stage185_derivatives_review_gate import DerivativesReviewReceipt
from nexus_titan.data.stage186_quote_tape import TapeQuote, audit_quote_tape
from nexus_titan.data.stage187_causal_signal import SignalIntent
from nexus_titan.data.stage188_synthetic_fill import SyntheticFillEvent
from nexus_titan.data.stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from nexus_titan.data.stage192_equity_drawdown import audit_equity_drawdown
from nexus_titan.data.stage193_cost_stress import audit_extra_cost_stress
from nexus_titan.data.stage194_holdout_trade_split import audit_holdout_trade_split
from nexus_titan.data.stage195_offline_portfolio_gate import evaluate_offline_portfolio_gate

UTC = timezone.utc
T = datetime(2026, 11, 1, tzinfo=UTC)
CONFIG = 'c' * 64


def trades():
    days = (0, 1, 10, 11)
    pnls = ('12', '-4', '3', '8')
    return tuple(ClosedReplay('trade_' + str(i), T + timedelta(days=d),
                             E2EPaperReplayReceipt(True, Decimal(p), format(i + 1, '064x'), ()))
                 for i, (d, p) in enumerate(zip(days, pnls)))


def receipts(t=None, **equity_opts):
    t = trades() if t is None else t
    ledger = audit_portfolio_replay_ledger(t)
    equity = audit_equity_drawdown(t, ledger=ledger, opening_equity=equity_opts.get('opening_equity', '1000'),
                                  max_drawdown_bps=equity_opts.get('max_drawdown_bps', 9000))
    costs = audit_extra_cost_stress(t, ledger=ledger, extra_cost_per_roundtrip='2', max_acceptable_loss='50')
    split = audit_holdout_trade_split(t, ledger=ledger, train_end=T + timedelta(days=2),
                                     holdout_start=T + timedelta(days=5))
    return ledger, equity, costs, split


def gate(*, items=None, **mod):
    ledger, equity, costs, split = receipts() if items is None else items
    args = dict(ledger=ledger, equity=equity, costs=costs, split=split,
                config_sha256=CONFIG, provenance_attested=True,
                independent_risk_veto_attested=True, holdout_separation_attested=True)
    args.update(mod)
    return evaluate_offline_portfolio_gate(**args)


def test_stage191_valid_deterministic_ledger():
    r = audit_portfolio_replay_ledger(trades())
    assert r.accepted and r.trade_count == 4 and r.net_pnl == Decimal('19')
    assert len(r.ledger_sha256) == 64 and r == audit_portfolio_replay_ledger(trades())


def test_stage191_timezone_equivalence():
    offset = timezone(timedelta(hours=5, minutes=30))
    t = tuple(replace(row, closed_at=row.closed_at.astimezone(offset)) for row in trades())
    assert audit_portfolio_replay_ledger(t) == audit_portfolio_replay_ledger(trades())


@pytest.mark.parametrize('broken', [
    lambda t: (), lambda t: list(t), lambda t: t * 1251,
    lambda t: (replace(t[0], trade_id='bad id'),) + t[1:],
    lambda t: (replace(t[0], trade_id=''),) + t[1:],
    lambda t: (replace(t[1], trade_id=t[0].trade_id),) + t[1:],
    lambda t: (replace(t[1], receipt=replace(t[1].receipt, replay_sha256=t[0].receipt.replay_sha256)),) + t[1:],
    lambda t: (replace(t[0], closed_at=t[0].closed_at.replace(tzinfo=None)),) + t[1:],
    lambda t: (replace(t[0], closed_at=t[1].closed_at),) + t[1:],
    lambda t: (replace(t[1], closed_at=t[0].closed_at),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, blockers=('invalid',))),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, accepted_for_offline_paper_review=False)),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, live_trading_authorized=True)),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, autonomous_execution_authorized=True)),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, strategy_promotion_authorized=True)),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, replay_sha256='broken')),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, net_pnl=Decimal('NaN'))),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, net_pnl=Decimal('1e25'))),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, net_pnl=Decimal('0.000000001'))),) + t[1:],
])
def test_stage191_corruption_rejected(broken):
    assert not audit_portfolio_replay_ledger(broken(trades())).accepted


def test_stage192_equity_reconciles_and_drawdown():
    ledger, equity, _, _ = receipts()
    assert equity.accepted and equity.ledger_sha256 == ledger.ledger_sha256
    assert equity.ending_equity == Decimal('1019') and equity.max_drawdown_bps > 0
    assert len(equity.equity_sha256) == 64


@pytest.mark.parametrize('opening,limit', [
    ('0', 10000), ('-1', 10000), ('NaN', 10000), (True, 10000),
    ('100', True), ('100', -1), ('100', 10001), ('1.123456789', 10000),
])
def test_stage192_rejects_invalid_capital_or_limits(opening, limit):
    l = audit_portfolio_replay_ledger(trades())
    assert not audit_equity_drawdown(trades(), ledger=l, opening_equity=opening,
                                    max_drawdown_bps=limit).accepted


def test_stage192_depletion_and_risk_limit_block():
    t = trades()
    losing = (replace(t[0], receipt=replace(t[0].receipt, net_pnl=Decimal('-5'))),) + t[1:]
    l_loss = audit_portfolio_replay_ledger(losing)
    assert not audit_equity_drawdown(losing, ledger=l_loss, opening_equity='1', max_drawdown_bps=10000).accepted
    l = audit_portfolio_replay_ledger(t)
    assert not audit_equity_drawdown(trades(), ledger=l, opening_equity='1000', max_drawdown_bps=1).accepted


def test_stage192_tampered_ledger_blocked():
    l = audit_portfolio_replay_ledger(trades())
    assert not audit_equity_drawdown(trades(), ledger=replace(l, trade_count=3),
                                    opening_equity='1000', max_drawdown_bps=9000).accepted


def test_stage193_extra_cost_stress_changes_net():
    l, _, c, _ = receipts()
    assert c.accepted and c.ledger_sha256 == l.ledger_sha256
    assert c.stressed_net_pnl == Decimal('11')
    assert len(c.cost_sha256) == 64


@pytest.mark.parametrize('cost,limit', [
    ('NaN', '20'), ('-1', '20'), ('0.000000001', '20'), (5, '20'),
    ('5', '-1'), ('5', 'NaN'), ('5', '0.000000001'), ('5', True),
])
def test_stage193_invalid_costs_fail_closed(cost, limit):
    l = audit_portfolio_replay_ledger(trades())
    assert not audit_extra_cost_stress(trades(), ledger=l, extra_cost_per_roundtrip=cost,
                                       max_acceptable_loss=limit).accepted


def test_stage193_strict_loss_cap():
    l = audit_portfolio_replay_ledger(trades())
    result = audit_extra_cost_stress(trades(), ledger=l, extra_cost_per_roundtrip='20',
                                     max_acceptable_loss='10')
    assert not result.accepted and result.stressed_net_pnl == Decimal('-61')


def test_stage193_mutated_ledger_fails():
    l = audit_portfolio_replay_ledger(trades())
    assert not audit_extra_cost_stress(trades(), ledger=replace(l, ledger_sha256='0'*64),
                                       extra_cost_per_roundtrip='2', max_acceptable_loss='50').accepted


def test_stage194_holdout_groups_and_hash():
    l, _, _, s = receipts()
    assert s.accepted and (s.train_count, s.holdout_count) == (2, 2)
    assert (s.train_net_pnl, s.holdout_net_pnl) == (Decimal('8'), Decimal('11'))
    assert s.ledger_sha256 == l.ledger_sha256 and len(s.split_sha256) == 64


@pytest.mark.parametrize('change', [
    {'embargo_days': True}, {'embargo_days': 0}, {'embargo_days': 366},
    {'min_holdout_trades': True}, {'min_holdout_trades': 0}, {'min_holdout_trades': 5},
    {'train_end': T + timedelta(days=10)},
    {'holdout_start': T + timedelta(days=2)},
    {'train_end': T + timedelta(days=2), 'holdout_start': T + timedelta(days=2, hours=2)},
    {'train_end': T + timedelta(days=10, hours=1), 'holdout_start': T + timedelta(days=12)},
    {'train_end': datetime(2026, 11, 1)},
])
def test_stage194_invalid_split_or_embargo(change):
    t = trades(); l = audit_portfolio_replay_ledger(t)
    args = dict(ledger=l, train_end=T+timedelta(days=2), holdout_start=T+timedelta(days=5))
    args.update(change)
    assert not audit_holdout_trade_split(t, **args).accepted


def test_stage195_combines_linked_evidence():
    r = gate()
    assert r.accepted_for_synthetic_research_review and len(r.evidence_sha256) == 64
    assert (r.live_trading_authorized, r.autonomous_execution_authorized,
            r.strategy_promotion_authorized) == (False, False, False)
    assert r == gate()


@pytest.mark.parametrize('flag', [
    'provenance_attested', 'independent_risk_veto_attested', 'holdout_separation_attested'
])
def test_stage195_denies_missing_attestation(flag):
    assert not gate(**{flag: False}).accepted_for_synthetic_research_review


@pytest.mark.parametrize('flag', ['live_requested', 'autonomous_requested', 'promotion_requested'])
def test_stage195_denies_high_risk_request(flag):
    r = gate(**{flag: True})
    assert not r.accepted_for_synthetic_research_review and not r.evidence_sha256
    assert not r.live_trading_authorized


@pytest.mark.parametrize('component,mutator', [
    (0, lambda x: replace(x, trade_count=999)),
    (1, lambda x: replace(x, ledger_sha256='a'*64)),
    (2, lambda x: replace(x, cost_sha256='')),
    (3, lambda x: replace(x, split_sha256='')),
])
def test_stage195_invalid_evidence_rejected(component, mutator):
    values = list(receipts())
    values[component] = mutator(values[component])
    assert not gate(items=values).accepted_for_synthetic_research_review


def test_stage195_bad_config_fingerprint():
    assert not gate(config_sha256='A'*64).accepted_for_synthetic_research_review


def test_stage195_denies_partial_holdout():
    values = list(receipts())
    values[3] = replace(values[3], holdout_count=1)
    assert not gate(items=values).accepted_for_synthetic_research_review


def test_stage190_to_195_real_synthetic_integration():
    """Stage 190 actual synthetic path, not just a hand-built receipt."""
    t = datetime(2026, 11, 12, 9, tzinfo=UTC)
    contract = 'NIFTY:2026-11-26:CE:24000'
    dataset = 'a' * 64
    quotes = (TapeQuote('q1',t,t+timedelta(milliseconds=100),'99','100',10,10),
              TapeQuote('q2',t+timedelta(seconds=10),t+timedelta(seconds=10,milliseconds=100),'110','111',10,10))
    tp = audit_quote_tape(quotes,contract_id=contract,dataset_sha256=dataset)
    e = SignalIntent('buy','NIFTY:2026-11-26:CE:24000',dataset,tp.tape_sha256,'q1',t+timedelta(milliseconds=200),'BUY',2,100)
    x = SignalIntent('sell','NIFTY:2026-11-26:CE:24000',dataset,tp.tape_sha256,'q2',t+timedelta(seconds=10,milliseconds=200),'SELL',2,100)
    result = replay_synthetic_roundtrip(quotes=quotes,contract_id=contract,dataset_sha256=dataset,
           entry_signal=e,exit_signal=x,
           entry_fills=(SyntheticFillEvent('f1','buy',t+timedelta(milliseconds=300),2,'100'),),
           exit_fills=(SyntheticFillEvent('f2','sell',t+timedelta(seconds=10,milliseconds=300),2,'110'),),
           contract_multiplier=1,entry_fees='1',exit_fees='1',
           independent_review=DerivativesReviewReceipt(True,(),False,False,False),
           source_independently_verified=True,contract_independently_verified=True,
           fee_schedule_independently_verified=True,risk_veto_independently_verified=True)
    assert result.accepted_for_offline_paper_review
    rows = (ClosedReplay('real_stage190_synthetic',t+timedelta(days=15),result),)
    checked = audit_portfolio_replay_ledger(rows)
    assert checked.accepted and checked.net_pnl == result.net_pnl == Decimal('18')
