from datetime import datetime, timedelta, timezone
from decimal import Decimal
from nexus_titan.data.stage166_backtest_alignment import audit_signal_alignment
from nexus_titan.data.stage167_execution_fill_bounds import audit_fill
from nexus_titan.data.stage168_trade_reconciliation import reconcile_quantities
from nexus_titan.data.stage169_performance_sanity import audit_closed_trades
from nexus_titan.data.stage170_backtest_evidence_gate import evaluate_backtest_evidence

T = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)

def test_166_valid():
    assert audit_signal_alignment((T,T+timedelta(minutes=1)), ((T+timedelta(minutes=1),T),)).accepted

def test_166_lookahead():
    assert not audit_signal_alignment((T,T+timedelta(minutes=1)), ((T,T+timedelta(minutes=1)),)).accepted

def test_166_unsorted():
    assert not audit_signal_alignment((T,T), ((T,T),)).accepted

def test_167_valid():
    assert audit_fill(side='BUY', reference_price=100, fill_price=100.05, max_adverse_bps=10).accepted

def test_167_excessive_slippage():
    assert not audit_fill(side='SELL', reference_price=100, fill_price=99, max_adverse_bps=10).accepted

def test_167_nan():
    assert not audit_fill(side='BUY', reference_price=float('nan'), fill_price=100, max_adverse_bps=10).accepted

def test_168_valid():
    assert reconcile_quantities('5', ('2', '3')).accepted

def test_168_partial():
    assert not reconcile_quantities('5', ('2',)).accepted

def test_168_overfill():
    assert not reconcile_quantities('5', ('3','3')).accepted

def test_169_valid():
    assert audit_closed_trades(('100', '-20'), ('5','5')).net_pnl == Decimal('70')

def test_169_negative_cost():
    assert not audit_closed_trades(('100',), ('-1',)).accepted

def test_169_mismatch():
    assert not audit_closed_trades(('100',), ()).accepted

def test_170_pass():
    assert evaluate_backtest_evidence(alignment=audit_signal_alignment((T,),((T,T),)),
        fill=audit_fill(side='BUY',reference_price=100,fill_price=100,max_adverse_bps=1),
        reconciliation=reconcile_quantities('1',('1',)),
        performance=audit_closed_trades(('10',),('1',)),dataset_verified=True).accepted_for_offline_review

def test_170_unverified_dataset():
    r=evaluate_backtest_evidence(alignment=audit_signal_alignment((T,),((T,T),)),
        fill=audit_fill(side='BUY',reference_price=100,fill_price=100,max_adverse_bps=1),
        reconciliation=reconcile_quantities('1',('1',)),
        performance=audit_closed_trades(('10',),('1',)),dataset_verified=False)
    assert 'dataset' in r.blockers

def test_170_live_prohibited():
    r=evaluate_backtest_evidence(alignment=audit_signal_alignment((T,),((T,T),)),
        fill=audit_fill(side='BUY',reference_price=100,fill_price=100,max_adverse_bps=1),
        reconciliation=reconcile_quantities('1',('1',)),
        performance=audit_closed_trades(('10',),('1',)),dataset_verified=True,live_requested=True)
    assert not r.accepted_for_offline_review
