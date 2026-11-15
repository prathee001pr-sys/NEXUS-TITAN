"""Stage 181-185 synthetic unit tests; no market-data authenticity claims."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.stage174_walkforward_purge import Fold, audit_walkforward_folds
from nexus_titan.data.stage180_paper_evidence_gate import PaperEvidenceReceipt
from nexus_titan.data.stage181_order_lifecycle import (
    OrderEvent, audit_order_lifecycle,
)
from nexus_titan.data.stage182_option_legs import OptionLeg, audit_option_legs
from nexus_titan.data.stage183_option_stress import audit_option_stress
from nexus_titan.data.stage184_oos_stability import (
    OOSFoldMetric, audit_oos_stability,
)
from nexus_titan.data.stage185_derivatives_review_gate import evaluate_derivatives_review

T = datetime(2026, 11, 12, 9, 15, tzinfo=timezone.utc)
ASOF = date(2026, 11, 12)
SHA = 'a' * 64


def events():
    return (OrderEvent('evt1', 'o1', 'SUBMITTED', T),
            OrderEvent('evt2', 'o1', 'FILL', T + timedelta(seconds=1), '65'))


def legs():
    return (
        OptionLeg('NIFTY', date(2026, 11, 26), 'CE', '24000', 'BUY', 65, 1, '100'),
        OptionLeg('NIFTY', date(2026, 11, 26), 'CE', '24100', 'SELL', 65, 1, '80'),
    )


def valid_walkforward():
    d = lambda day: datetime(2026, 1, day, tzinfo=timezone.utc)
    folds = (
        Fold(d(1), d(3), d(5), d(7)),
        Fold(d(8), d(10), d(13), d(16)),
    )
    return audit_walkforward_folds(folds, embargo_minutes=60)


def oos_metrics():
    return (OOSFoldMetric(0, 15, True, '100', 100, SHA),
            OOSFoldMetric(1, 15, True, '80', 200, SHA))


def oos(**kwargs):
    p = dict(walkforward=valid_walkforward(), dataset_sha256=SHA,
             min_trades_per_fold=10, min_positive_fold_ratio_bps=7500,
             max_drawdown_bps=250, metrics_independently_verified=True)
    p.update(kwargs)
    return audit_oos_stability(oos_metrics(), **p)


def stress(**kwargs):
    p = dict(asof=ASOF, exposure=audit_option_legs(legs(), asof=ASOF, lot_size_verified=True),
             scenario_marks=(('120', '50'), ('90', '90')),
             scenario_costs=('10', '10'), max_sampled_loss='2000',
             marks_verified=True, costs_verified=True, lot_size_verified=True)
    p.update(kwargs)
    return audit_option_stress(legs(), **p)


def final(**kwargs):
    p = dict(prior=PaperEvidenceReceipt(True, (), False, False),
             lifecycle=audit_order_lifecycle('o1', '65', events()),
             legs=audit_option_legs(legs(), asof=ASOF, lot_size_verified=True),
             stress=stress(), oos=oos(),
             contract_metadata_independently_verified=True,
             dataset_provenance_independently_verified=True, dataset_sha256=SHA)
    p.update(kwargs)
    return evaluate_derivatives_review(**p)


def test_stage181_full_fill():
    r = audit_order_lifecycle('o1', '65', events())
    assert r.accepted and r.final_state == 'FILLED' and r.filled_quantity == Decimal('65')


def test_stage181_partial_then_cancel_valid_but_not_full():
    e = (events()[0], replace(events()[1], fill_quantity='25'),
         OrderEvent('evt3', 'o1', 'CANCELLED', T + timedelta(seconds=2)))
    r = audit_order_lifecycle('o1', '65', e)
    assert r.accepted and r.final_state == 'CANCELLED' and r.filled_quantity == 25
    assert not final(lifecycle=r).accepted_for_offline_paper_review


@pytest.mark.parametrize('mutator', [
    lambda e: (replace(e[0], at=e[0].at.replace(tzinfo=None)), e[1]),
    lambda e: (e[0], replace(e[1], event_id=e[0].event_id)),
    lambda e: (e[0], replace(e[1], order_id='other')),
    lambda e: (e[0], replace(e[1], at=e[0].at)),
    lambda e: (e[0], replace(e[1], fill_quantity='66')),
    lambda e: (e[0], replace(e[1], fill_quantity='NaN')),
    lambda e: (e[0], replace(e[1], kind='CANCELLED', fill_quantity='65')),
    lambda e: (replace(e[0], kind='FILL'), e[1]),
    lambda e: (e[0], replace(e[1], kind='SUBMITTED')),
    lambda e: (e[0], replace(e[1], kind='FILL', fill_quantity='0')),
])
def test_stage181_invalid_events(mutator):
    assert not audit_order_lifecycle('o1', '65', mutator(events())).accepted


def test_stage181_late_fill_rejected():
    e = events() + (OrderEvent('evt3', 'o1', 'FILL', T + timedelta(seconds=3), '1'),)
    assert not audit_order_lifecycle('o1', '65', e).accepted


def test_stage181_missing_terminal_rejected():
    assert not audit_order_lifecycle('o1', '65',
        (events()[0], replace(events()[1], fill_quantity='20'))).accepted


def test_stage182_option_spread():
    r = audit_option_legs(legs(), asof=ASOF, lot_size_verified=True)
    assert r.accepted and r.net_premium_cash == Decimal('-1300')
    assert r.gross_premium_cash == Decimal('11700') and len(r.legs_sha256) == 64


@pytest.mark.parametrize('mutator', [
    lambda x: (replace(x[0], symbol='SPX'), x[1]),
    lambda x: (replace(x[0], expiry=date(2026, 11, 11)), x[1]),
    lambda x: (replace(x[0], option_type='XX'), x[1]),
    lambda x: (replace(x[0], side='HOLD'), x[1]),
    lambda x: (replace(x[0], strike='NaN'), x[1]),
    lambda x: (replace(x[0], entry_premium='0'), x[1]),
    lambda x: (replace(x[0], lot_size=True), x[1]),
    lambda x: (replace(x[0], lots=0), x[1]),
    lambda x: (x[0], replace(x[1], symbol='BANKNIFTY')),
    lambda x: (x[0], replace(x[1], expiry=date(2026, 12, 3))),
    lambda x: (x[0], replace(x[0], side='SELL')),
])
def test_stage182_invalid_legs(mutator):
    assert not audit_option_legs(mutator(legs()), asof=ASOF, lot_size_verified=True).accepted


def test_stage182_lot_size_must_be_verified():
    assert not audit_option_legs(legs(), asof=ASOF, lot_size_verified=False).accepted


def test_stage183_scenarios():
    r = stress()
    assert r.accepted and r.scenario_count == 2 and r.worst_scenario_loss == 1310


@pytest.mark.parametrize('change', [
    {'max_sampled_loss': '1000'},
    {'marks_verified': False},
    {'costs_verified': False},
    {'scenario_marks': (('120',), ('90', '90'))},
    {'scenario_marks': (('120', '50'), ('NaN', '90'))},
    {'scenario_costs': ('10',)},
    {'scenario_costs': ('-2', '10')},
    {'max_sampled_loss': '0'},
    {'lot_size_verified': False},
])
def test_stage183_bad_scenarios(change):
    assert not stress(**change).accepted


def test_stage183_forged_exposure_cannot_pass():
    ex = audit_option_legs(legs(), asof=ASOF, lot_size_verified=True)
    assert not stress(exposure=replace(ex, gross_premium_cash=Decimal('1'))).accepted


def test_stage184_oos_stability():
    r = oos()
    assert r.accepted and r.checked_folds == 2 and r.positive_fold_ratio_bps == 10000


@pytest.mark.parametrize('change', [
    {'metrics_independently_verified': False},
    {'dataset_sha256': 'XYZ'},
    {'min_trades_per_fold': 16},
    {'min_positive_fold_ratio_bps': 10001},
    {'max_drawdown_bps': 150},
])
def test_stage184_invalid_policy_or_metrics(change):
    assert not oos(**change).accepted


def test_stage184_mismatched_metrics():
    m = oos_metrics()
    kwargs = dict(walkforward=valid_walkforward(), dataset_sha256=SHA,
                  min_trades_per_fold=10, min_positive_fold_ratio_bps=5000,
                  max_drawdown_bps=300, metrics_independently_verified=True)
    bad = (m[0], replace(m[1], dataset_sha256='b' * 64))
    assert not audit_oos_stability(bad, **kwargs).accepted
    bad = (m[0], replace(m[1], profitable=False))
    assert not audit_oos_stability(bad, **kwargs).accepted
    bad = (m[0], replace(m[1], fold_number=0))
    assert not audit_oos_stability(bad, **kwargs).accepted


def test_stage184_negative_pnl_correctly_classified():
    m = oos_metrics()
    negative = (m[0], replace(m[1], net_pnl='-10', profitable=False))
    r = audit_oos_stability(negative, walkforward=valid_walkforward(), dataset_sha256=SHA,
        min_trades_per_fold=10, min_positive_fold_ratio_bps=5000,
        max_drawdown_bps=250, metrics_independently_verified=True)
    assert r.accepted and r.positive_fold_ratio_bps == 5000


def test_stage185_accepts_only_offline_review():
    r = final()
    assert r.accepted_for_offline_paper_review
    assert r.live_trading_authorized is False
    assert r.autonomous_execution_authorized is False
    assert r.strategy_promotion_authorized is False


@pytest.mark.parametrize('change', [
    {'contract_metadata_independently_verified': False},
    {'dataset_provenance_independently_verified': False},
    {'dataset_sha256': 'b' * 64},
    {'live_requested': True},
    {'promotion_requested': True},
    {'autonomous_requested': True},
    {'prior': None},
    {'lifecycle': None},
    {'legs': None},
    {'stress': None},
    {'oos': None},
])
def test_stage185_fail_closed(change):
    r = final(**change)
    assert not r.accepted_for_offline_paper_review
    assert not r.live_trading_authorized


def test_stage185_tampered_prior_or_stress():
    assert not final(prior=PaperEvidenceReceipt(True, (), True, False)).accepted_for_offline_paper_review
    assert not final(stress=replace(stress(), blockers=('tampered',))).accepted_for_offline_paper_review
    assert not final(stress=replace(stress(), legs_sha256='b' * 64)).accepted_for_offline_paper_review
