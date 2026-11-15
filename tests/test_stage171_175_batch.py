"""Focused deterministic offline safety tests for Stages 171–175."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.stage170_backtest_evidence_gate import EvidenceReceipt
from nexus_titan.data.stage171_execution_timing import audit_execution_timing
from nexus_titan.data.stage172_replay_integrity import audit_event_replay
from nexus_titan.data.stage173_settlement_ledger import audit_roundtrip_settlement
from nexus_titan.data.stage174_walkforward_purge import Fold, audit_walkforward_folds
from nexus_titan.data.stage175_offline_review_gate import evaluate_offline_review

T = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)


def timing(**kwargs):
    values = dict(observation_at=T, decision_at=T + timedelta(milliseconds=100),
                  submitted_at=T + timedelta(milliseconds=200),
                  filled_at=T + timedelta(milliseconds=300),
                  max_observation_age_ms=500, max_execution_latency_ms=500)
    values.update(kwargs)
    return audit_execution_timing(**values)


def test_171_causal_timing():
    assert timing().accepted


@pytest.mark.parametrize('overrides,expected', [
    ({'observation_at': T + timedelta(seconds=1)}, 'lookahead'),
    ({'decision_at': T + timedelta(seconds=1)}, 'submitted before'),
    ({'filled_at': T}, 'fill before'),
    ({'decision_at': T + timedelta(seconds=2), 'submitted_at': T + timedelta(seconds=2)}, 'stale'),
    ({'filled_at': T + timedelta(seconds=2)}, 'latency'),
    ({'max_observation_age_ms': True}, 'invalid timing'),
    ({'observation_at': T.replace(tzinfo=None)}, 'timezone-aware'),
])
def test_171_rejections(overrides, expected):
    receipt = timing(**overrides)
    assert not receipt.accepted
    assert expected in ' '.join(receipt.blockers)


def test_172_different_orders_and_ordered_events():
    assert audit_event_replay((('a', 'order1', 0), ('b', 'order2', 0), ('c', 'order1', 1))).accepted


@pytest.mark.parametrize('events,expected', [
    ((('a','o',0), ('a','o',1)), 'duplicate event id'),
    ((('a','o',1), ('b','o',1)), 'order sequence'),
    ((('a','o',2), ('b','o',1)), 'order sequence'),
    ((('a','o',True),), 'invalid fields'),
    ((('', 'o', 0),), 'invalid fields'),
    (((1, 'o', 0),), 'invalid fields'),
    ((), 'missing'),
])
def test_172_rejections(events, expected):
    r = audit_event_replay(events)
    assert not r.accepted
    assert expected in ' '.join(r.blockers)


def test_172_event_size_cap():
    assert not audit_event_replay((('a','o',0), ('b','o',1)), max_events=1).accepted


def settle(**kwargs):
    vals = dict(entry_side='BUY', entry_price='100.50', exit_price='102.00',
                quantity='2', contract_multiplier=25,
                entry_fees='5.25', exit_fees='4.75')
    vals.update(kwargs)
    return audit_roundtrip_settlement(**vals)


def test_173_exact_long_pnl():
    r = settle()
    assert r.accepted and r.gross_pnl == Decimal('75.00') and r.net_pnl == Decimal('65.00')


def test_173_short_loss_and_costs():
    r = settle(entry_side='SELL', exit_price='102.00')
    assert r.accepted and r.net_pnl == Decimal('-85.00')


@pytest.mark.parametrize('overrides', [
    {'entry_price': '0'}, {'exit_price': 'NaN'}, {'quantity': '0'},
    {'entry_fees': '-1'}, {'contract_multiplier': True},
    {'entry_side': 'HOLD'}, {'exit_price': '1e99'}, {'quantity': '1'*50},
    {'entry_price': 100.5},
])
def test_173_fails_closed(overrides):
    assert not settle(**overrides).accepted


def fold(train_days, label_days, test_days, end_days):
    return Fold(T + timedelta(days=train_days), T + timedelta(days=label_days),
                T + timedelta(days=test_days), T + timedelta(days=end_days))


def test_174_walkforward_valid():
    f = (fold(0,5,7,8),fold(0,9,11,12))
    assert audit_walkforward_folds(f, embargo_minutes=60).accepted


def test_174_reject_leaky_labels():
    assert not audit_walkforward_folds((fold(0,7,7,8),), embargo_minutes=0).accepted


def test_174_reject_embargo_boundary():
    f=(Fold(T, T+timedelta(hours=1), T+timedelta(hours=2), T+timedelta(hours=3)),)
    assert not audit_walkforward_folds(f, embargo_minutes=60).accepted


def test_174_reject_overlapping_test_windows():
    assert not audit_walkforward_folds((fold(0,1,3,5),fold(1,4,5,6)),embargo_minutes=0).accepted


def test_174_reject_naive_and_negative_embargo():
    f=(Fold(T.replace(tzinfo=None), T, T+timedelta(days=1), T+timedelta(days=2)),)
    assert not audit_walkforward_folds(f, embargo_minutes=1).accepted
    assert not audit_walkforward_folds((fold(0,1,3,4),),embargo_minutes=-1).accepted


def approved():
    return evaluate_offline_review(evidence=EvidenceReceipt(True,()), timing=timing(),
        replay=audit_event_replay((('id1','ord1',0),)), settlement=settle(),
        walkforward=audit_walkforward_folds((fold(0,1,3,4),),embargo_minutes=60),
        dataset_provenance_verified=True, configuration_frozen=True)


def test_175_offline_review_only():
    r = approved()
    assert r.accepted_for_offline_review and not r.live_trading_authorized


def test_175_blocks_live_request():
    valid = dict(evidence=EvidenceReceipt(True,()), timing=timing(),
        replay=audit_event_replay((('id1','ord1',0),)), settlement=settle(),
        walkforward=audit_walkforward_folds((fold(0,1,3,4),),embargo_minutes=60),
        dataset_provenance_verified=True, configuration_frozen=True)
    r = evaluate_offline_review(**valid,live_requested=True)
    assert not r.accepted_for_offline_review and not r.live_trading_authorized
    assert 'live trading prohibited' in r.blockers


def test_175_blocks_unverified_and_forged_types():
    r=evaluate_offline_review(evidence=EvidenceReceipt(True,()),timing=timing(),
        replay=audit_event_replay((('id1','ord1',0),)), settlement=settle(),
        walkforward=audit_walkforward_folds((fold(0,1,3,4),),embargo_minutes=60),
        dataset_provenance_verified=1, configuration_frozen=True)
    assert not r.accepted_for_offline_review and 'dataset provenance' in r.blockers
    r=evaluate_offline_review(evidence=True,timing=True,replay=True,settlement=True,
        walkforward=True,dataset_provenance_verified=True,configuration_frozen=True)
    assert len(r.blockers) == 5 and not r.live_trading_authorized
