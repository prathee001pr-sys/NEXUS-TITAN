from dataclasses import replace
from types import SimpleNamespace as S
import pytest
from nexus_titan.operations.stage96_accounting_review import reconcile_fo_snapshot,FOAccountingBlocked


def base(opened=False):
    p=S(filled_quantity=10,open_quantity=10 if opened else 0,open_hold_cents=0,
        remaining_premium_cents=960 if opened else 0,
        remaining_entry_fees_cents=40 if opened else 0,realized_net_pnl_cents=0)
    return S(account_id='fo-a',journal_revision=3,journal_tip='a'*64,
             initial_cents=50000,cash_cents=49000 if opened else 50250,
             remaining_cost_basis_cents=1000 if opened else 0,
             realized_gross_pnl_cents=0 if opened else 300,
             realized_net_pnl_cents=0 if opened else 250,
             paid_fees_cents=40 if opened else 50,orders=(p,))

def valuation():
    return S(account_id='fo-a',journal_revision=3,journal_sha256='a'*64,
             market_evidence_verified=False,synthetic_only=True,live_trading_enabled=False,
             unrealized_net_pnl_cents=170,total_hypothetical_equity_cents=50170,
             portfolio_exposure_cents=1200,estimated_exit_cost_cents=30,open_quantity=10)

def test_closed_flat_ledger():
    x=reconcile_fo_snapshot(base())
    assert (x.realized_net_pnl_cents,x.synthetic_equity_cents,x.closed_position_count)==(250,50250,1)
    assert (x.profit_factor,x.max_drawdown_percent,x.expectancy_cents)==(None,None,None)
    assert not x.live_trading_enabled

def test_open_without_signed_mark_never_fabricates_equity():
    x=reconcile_fo_snapshot(base(True))
    assert x.unrealized_net_pnl_cents is None and x.net_pnl_cents is None

def test_open_with_verified_synthetic_provenance():
    x=reconcile_fo_snapshot(base(True),valuation())
    assert x.synthetic_equity_cents==50170 and x.unrealized_net_pnl_cents==170
    assert not x.market_evidence_verified

@pytest.mark.parametrize('change',[
    {'journal_sha256':'b'*64},{'journal_revision':4},{'market_evidence_verified':True},
    {'synthetic_only':False},{'live_trading_enabled':True},
    {'total_hypothetical_equity_cents':50171},{'open_quantity':9}
])
def test_reject_valuation_mismatch(change):
    v=valuation();v.__dict__.update(change)
    with pytest.raises(FOAccountingBlocked):reconcile_fo_snapshot(base(True),v)

@pytest.mark.parametrize('field,value',[
    ('cash_cents',49001),('journal_tip','broken'),('remaining_cost_basis_cents',1001),
    ('realized_net_pnl_cents',1),('initial_cents',True)
])
def test_corrupt_snapshot_fails_closed(field,value):
    s=base(True);setattr(s,field,value)
    with pytest.raises(FOAccountingBlocked):reconcile_fo_snapshot(s)
