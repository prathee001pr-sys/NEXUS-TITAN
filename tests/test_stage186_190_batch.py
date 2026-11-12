"""Offline synthetic E2E regression. These quotes/fills are NOT real NSE observations."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from nexus_titan.data.stage185_derivatives_review_gate import DerivativesReviewReceipt
from nexus_titan.data.stage186_quote_tape import TapeQuote, audit_quote_tape
from nexus_titan.data.stage187_causal_signal import SignalIntent, audit_causal_signal
from nexus_titan.data.stage188_synthetic_fill import SyntheticFillEvent, audit_synthetic_fills
from nexus_titan.data.stage189_synthetic_roundtrip import audit_synthetic_roundtrip
from nexus_titan.data.stage190_e2e_paper_replay import replay_synthetic_roundtrip

T = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
DATA = 'a' * 64
CONTRACT = 'NIFTY:2026-11-26:CE:24000'


def tape_quotes():
    return (
        TapeQuote('q1', T, T + timedelta(milliseconds=100), '99', '100', 10, 10),
        TapeQuote('q2', T + timedelta(seconds=10), T + timedelta(seconds=10, milliseconds=100), '110', '111', 10, 10),
    )


def tape(quotes=None, **changes):
    return audit_quote_tape(quotes if quotes is not None else tape_quotes(), contract_id=changes.get('contract_id', CONTRACT), dataset_sha256=changes.get('dataset_sha256', DATA))


def signal(side='BUY', quote_id=None, at=None, **changes):
    receipt = tape()
    return SignalIntent(changes.get('signal_id', f's_{side}'), changes.get('contract_id', CONTRACT),
                        changes.get('dataset_sha256', DATA), changes.get('tape_sha256', receipt.tape_sha256),
                        changes.get('quote_id', quote_id if quote_id is not None else ('q1' if side == 'BUY' else 'q2')), at if at is not None else T + timedelta(milliseconds=200) if side == 'BUY' else T + timedelta(seconds=10, milliseconds=200),
                        changes.get('side_override', side), changes.get('quantity', 2), changes.get('max_slippage_bps', 100))


def audited_signal(side='BUY', **changes):
    return audit_causal_signal(signal(side, **changes), quotes=tape_quotes(), tape=tape())


def fill_events(side='BUY'):
    at = T + timedelta(milliseconds=300) if side == 'BUY' else T + timedelta(seconds=10, milliseconds=300)
    return (SyntheticFillEvent(f'fill_{side}', f's_{side}', at, 2, '100' if side == 'BUY' else '110'),)


def fills(side='BUY', **changes):
    return audit_synthetic_fills(changes.get('events', fill_events(side)), signal=changes.get('signal', audited_signal(side)), max_latency_ms=changes.get('max_latency_ms', 5000))


def roundtrip(**changes):
    return audit_synthetic_roundtrip(entry=changes.get('entry', fills('BUY')),
                                    exit=changes.get('exit', fills('SELL')),
                                    multiplier=changes.get('multiplier', 1),
                                    entry_fees=changes.get('entry_fees', '1'),
                                    exit_fees=changes.get('exit_fees', '1'))


def replay(**changes):
    args = dict(quotes=tape_quotes(), contract_id=CONTRACT, dataset_sha256=DATA,
                entry_signal=signal('BUY'), entry_fills=fill_events('BUY'),
                exit_signal=signal('SELL'), exit_fills=fill_events('SELL'),
                contract_multiplier=1, entry_fees='1', exit_fees='1',
                independent_review=DerivativesReviewReceipt(True, (), False, False, False),
                source_independently_verified=True,
                contract_independently_verified=True,
                fee_schedule_independently_verified=True,
                risk_veto_independently_verified=True)
    args.update(changes)
    return replay_synthetic_roundtrip(**args)


def test_stage186_tape_valid_hash_stable():
    a = tape()
    assert a.accepted and len(a.tape_sha256) == 64 and a.quote_count == 2
    assert a == tape()


def test_stage186_same_instant_different_timezone_same_hash():
    z = timezone(timedelta(hours=5, minutes=30))
    qs = tuple(replace(q, observed_at=q.observed_at.astimezone(z), available_at=q.available_at.astimezone(z)) for q in tape_quotes())
    assert tape(qs).tape_sha256 == tape().tape_sha256


@pytest.mark.parametrize('options', [
    {'dataset_sha256': 'bad'}, {'contract_id': 'bad/id'},
    {'contract_id': ''}, {'dataset_sha256': 'A' * 64},
])
def test_stage186_invalid_scope(options):
    assert not tape(**options).accepted


@pytest.mark.parametrize('mutator', [
    lambda x: x[:1],
    lambda x: x + (x[-1],),
    lambda x: (x[0], replace(x[1], quote_id=x[0].quote_id)),
    lambda x: (x[0], replace(x[1], observed_at=x[0].observed_at)),
    lambda x: (x[0], replace(x[1], available_at=x[0].available_at)),
    lambda x: (x[0], replace(x[1], bid='120')),
    lambda x: (x[0], replace(x[1], bid='NaN')),
    lambda x: (x[0], replace(x[1], ask='0')),
    lambda x: (x[0], replace(x[1], bid_quantity=True)),
    lambda x: (x[0], replace(x[1], ask_quantity=-1)),
    lambda x: (x[0], replace(x[1], quote_id='***')),
    lambda x: (x[0], replace(x[1], observed_at=x[1].observed_at.replace(tzinfo=None))),
    lambda x: (x[0], replace(x[1], available_at=x[1].observed_at - timedelta(seconds=1))),
])
def test_stage186_invalid_quote_rejected(mutator):
    assert not tape(mutator(tape_quotes())).accepted


def test_stage187_valid_entry_and_exit():
    assert audited_signal('BUY').accepted
    assert audited_signal('SELL').accepted


@pytest.mark.parametrize('changes', [
    {'side_override': 'OPEN'}, {'quantity': True}, {'quantity': 0},
    {'quantity': 1000001}, {'signal_id': ''}, {'max_slippage_bps': 1001},
    {'dataset_sha256': 'b' * 64}, {'contract_id': 'BANKNIFTY'},
    {'tape_sha256': 'b' * 64}, {'quote_id': 'q2'},
])
def test_stage187_invalid_signal_rejected(changes):
    assert not audited_signal('BUY', **changes).accepted


def test_stage187_stale_quote_blocked():
    a = audit_causal_signal(signal('BUY', at=T + timedelta(seconds=4)), quotes=tape_quotes(), tape=tape())
    assert not a.accepted and 'stale' in str(a.blockers)


def test_stage187_future_quote_blocked():
    a = audit_causal_signal(signal('BUY', at=T), quotes=tape_quotes(), tape=tape())
    assert not a.accepted


def test_stage187_forged_tape_blocked():
    qs = (tape_quotes()[0], replace(tape_quotes()[1], ask='150'))
    assert not audit_causal_signal(signal('BUY'), quotes=qs, tape=tape()).accepted


def test_stage188_full_fill():
    r = fills()
    assert r.accepted and r.fully_filled and r.quantity == 2 and r.average_price == Decimal('100')
    assert len(r.fills_sha256) == 64


def test_stage188_partial_not_full():
    q = replace(fill_events()[0], quantity=1)
    r = fills(events=(q,))
    assert r.accepted and not r.fully_filled and r.quantity == 1
    assert not roundtrip(entry=r).accepted


@pytest.mark.parametrize('mutator', [
    lambda e: (replace(e[0], signal_id='other'),),
    lambda e: (replace(e[0], event_id=''),),
    lambda e: (replace(e[0], quantity=True),),
    lambda e: (replace(e[0], quantity=11),),
    lambda e: (replace(e[0], quantity=0),),
    lambda e: (replace(e[0], execution_price='NaN'),),
    lambda e: (replace(e[0], execution_price='200'),),
    lambda e: (replace(e[0], execution_price='90'),),
    lambda e: (replace(e[0], filled_at=T - timedelta(seconds=1)),),
    lambda e: (replace(e[0], filled_at=T + timedelta(seconds=8)),),
    lambda e: (replace(e[0], filled_at=T.replace(tzinfo=None)),),
    lambda e: e + e,
])
def test_stage188_invalid_fill_rejected(mutator):
    assert not fills(events=mutator(fill_events())).accepted


def test_stage188_depth_rejected_even_if_signal_quantity_larger():
    s = audited_signal('BUY', quantity=11)
    e = replace(fill_events()[0], quantity=11)
    assert s.accepted and not fills(signal=s, events=(e,)).accepted


def test_stage188_slippage_bound():
    e = replace(fill_events()[0], execution_price='100.5')
    assert fills(events=(e,)).accepted
    e2 = replace(e, execution_price='102')
    assert not fills(events=(e2,)).accepted


def test_stage189_valid_net_settlement():
    r = roundtrip()
    assert r.accepted and r.settlement.net_pnl == Decimal('18')
    assert r.settlement.gross_pnl == Decimal('20')


@pytest.mark.parametrize('mod', [
    {'exit': fills('BUY')},
    {'entry': fills('SELL')},
    {'entry_fees': '-1'},
    {'exit_fees': 'NaN'},
    {'multiplier': True},
    {'multiplier': 0},
])
def test_stage189_bad_settlement_rejected(mod):
    assert not roundtrip(**mod).accepted


def test_stage189_quantity_mismatch_rejected():
    exit_s = audited_signal('SELL', quantity=1)
    exit_f = fills('SELL', signal=exit_s, events=(replace(fill_events('SELL')[0], quantity=1),))
    assert exit_f.fully_filled
    assert not roundtrip(exit=exit_f).accepted


def test_stage189_provenance_mismatch_rejected():
    assert not roundtrip(exit=replace(fills('SELL'), dataset_sha256='b' * 64)).accepted


def test_stage189_missing_exit_rejected():
    exit_f = replace(fills('SELL'), fully_filled=False)
    assert not roundtrip(exit=exit_f).accepted


def test_stage190_full_synthetic_e2e_and_determinism():
    a, b = replay(), replay()
    assert a == b and a.accepted_for_offline_paper_review
    assert a.net_pnl == Decimal('18') and len(a.replay_sha256) == 64
    assert (a.live_trading_authorized, a.autonomous_execution_authorized,
            a.strategy_promotion_authorized) == (False, False, False)


@pytest.mark.parametrize('changes', [
    {'independent_review': None},
    {'independent_review': DerivativesReviewReceipt(True, (), True, False, False)},
    {'independent_review': DerivativesReviewReceipt(False, ('blocker',), False, False, False)},
    {'source_independently_verified': False},
    {'contract_independently_verified': False},
    {'fee_schedule_independently_verified': False},
    {'risk_veto_independently_verified': False},
    {'live_requested': True},
    {'promotion_requested': True},
    {'autonomous_requested': True},
    {'dataset_sha256': 'b' * 64},
    {'entry_fills': (replace(fill_events('BUY')[0], quantity=1),)},
    {'exit_fills': (replace(fill_events('SELL')[0], execution_price='250'),)},
    {'entry_fees': '-0.1'},
    {'contract_multiplier': True},
])
def test_stage190_fail_closed(changes):
    r = replay(**changes)
    assert not r.accepted_for_offline_paper_review and r.net_pnl is None
    assert r.live_trading_authorized is False
    assert r.autonomous_execution_authorized is False
    assert r.strategy_promotion_authorized is False


def test_stage190_quote_mutation_breaks_quote_bound_signals():
    changed = (tape_quotes()[0], replace(tape_quotes()[1], ask='116'))
    r = replay(quotes=changed)
    assert not r.accepted_for_offline_paper_review


def test_stage190_short_roundtrip():
    # Short: sell at 99, buy at 90, 2 contracts, 1 + 1 fees => 16 net.
    qs = (TapeQuote('q1', T, T + timedelta(milliseconds=100), '99', '100', 10, 10),
          TapeQuote('q2', T + timedelta(seconds=10), T + timedelta(seconds=10, milliseconds=100), '89', '90', 10, 10))
    tp = tape(qs)
    e = replace(signal('SELL'), signal_id='short_entry', quote_id='q1',
                decision_at=T + timedelta(milliseconds=200), tape_sha256=tp.tape_sha256)
    x = replace(signal('BUY'), signal_id='short_exit', quote_id='q2',
                decision_at=T + timedelta(seconds=10, milliseconds=200), tape_sha256=tp.tape_sha256)
    ef = (SyntheticFillEvent('f1', 'short_entry', T + timedelta(milliseconds=300), 2, '99'),)
    xf = (SyntheticFillEvent('f2', 'short_exit', T + timedelta(seconds=10, milliseconds=300), 2, '90'),)
    r = replay(quotes=qs, entry_signal=e, exit_signal=x, entry_fills=ef, exit_fills=xf)
    assert r.accepted_for_offline_paper_review and r.net_pnl == Decimal('16')


def test_stage190_new_quote_before_fill_blocks():
    # Entry signal uses q1, but synthetic fill happens after q2 becomes available.
    late = (replace(fill_events('BUY')[0], filled_at=T + timedelta(seconds=10, milliseconds=200)),)
    assert not replay(entry_fills=late).accepted_for_offline_paper_review


def test_stage190_cross_leg_duplicate_fill_event_id_blocks():
    collision = (replace(fill_events('SELL')[0], event_id=fill_events('BUY')[0].event_id),)
    assert not replay(exit_fills=collision).accepted_for_offline_paper_review


def test_stage190_exit_signal_before_entry_completion_blocks():
    e = replace(signal('BUY'), decision_at=T + timedelta(milliseconds=200))
    x = replace(signal('SELL'), decision_at=T + timedelta(milliseconds=150), quote_id='q1')
    assert not replay(entry_signal=e, exit_signal=x).accepted_for_offline_paper_review


def test_stage188_duplicate_timestamp_blocks_even_distinct_event_ids():
    a = replace(fill_events('BUY')[0], quantity=1)
    b = replace(a, event_id='another')
    assert not fills(events=(a, b)).accepted
