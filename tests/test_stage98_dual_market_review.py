from types import SimpleNamespace as S
from dataclasses import replace
import pytest
from nexus_titan.operations.stage96_accounting_review import reconcile_fo_snapshot
from nexus_titan.operations.stage97_crypto_paper import CryptoPaperBook,CryptoPaperLimits,CryptoPaperIntent,CryptoPaperBlocked,seal_crypto_paper_permit
from nexus_titan.operations.stage98_dual_market_review import read_only_dual_market_review,DualMarketBlocked

def setup(tmp_path):
    p=S(filled_quantity=1,open_quantity=0,open_hold_cents=0,remaining_premium_cents=0,
        remaining_entry_fees_cents=0,realized_net_pnl_cents=100)
    s=S(account_id='indian-a',journal_revision=8,journal_tip='a'*64,initial_cents=100000,
        cash_cents=100100,remaining_cost_basis_cents=0,realized_gross_pnl_cents=120,
        realized_net_pnl_cents=100,paid_fees_cents=20,orders=(p,))
    indian=reconcile_fo_snapshot(s)
    b=CryptoPaperBook(path=tmp_path/'crypto.sqlite',account_id='crypto-a',
        limits=CryptoPaperLimits(200000,100000,150000,10000,paper_enabled=True),verification_key=b'z'*32,
        indian_book_path=tmp_path/'indian.sqlite')
    return indian,b

def test_two_isolated_currency_scorecards_no_conversion(tmp_path):
    i,b=setup(tmp_path)
    x=read_only_dual_market_review(i,b)
    assert (x.indian['currency'],x.crypto['currency'])==('INR','USDT')
    assert x.combined_pnl_cents is None and x.combined_cash_cents is None
    assert not x.live_trading_enabled

def test_crypto_kill_does_not_mutate_indian_scorecard(tmp_path):
    i,b=setup(tmp_path)
    before=read_only_dual_market_review(i,b)
    b.stop('emergency')
    after=read_only_dual_market_review(i,b)
    assert before.indian==after.indian
    assert after.crypto['kill_active'] and not before.crypto['kill_active']

@pytest.mark.parametrize('field,value',[
    ('currency','USDT'),('market','CRYPTO_PAPER'),('account_id','crypto-a'),
    ('live_trading_enabled',True),('journal_sha256','bad'),('cash_cents',99999)])
def test_fail_closed_on_invalid_indian_authority(tmp_path,field,value):
    i,b=setup(tmp_path)
    with pytest.raises(DualMarketBlocked):read_only_dual_market_review(replace(i,**{field:value}),b)

def test_broken_crypto_replay_blocks_cross_market_report(tmp_path):
    import sqlite3
    i,b=setup(tmp_path)
    with sqlite3.connect(b.path) as db:
        db.execute("UPDATE crypto_meta SET settings_sha='forged'")
    with pytest.raises(CryptoPaperBlocked):read_only_dual_market_review(i,b)


def test_crypto_many_restarts_conserve_separate_accounts(tmp_path):
    i,b=setup(tmp_path)
    key=b'z'*32
    for n in range(20):
        for side in ('BUY','SELL'):
            s=b.snapshot()
            intent=CryptoPaperIntent(f'op-{n}-{side}',side,1000,5000000,100+n)
            permit=seal_crypto_paper_permit(key,account_id=b.account_id,revision=s.journal_revision,
                                            tip=s.journal_tip,intent=intent,expires_epoch=110+n)
            b.apply(intent,permit,now_epoch=101+n,human_approved=True)
        b=CryptoPaperBook(path=b.path,account_id='crypto-a',limits=b.limits,verification_key=key,
                          indian_book_path=tmp_path/'indian.sqlite')
        review=read_only_dual_market_review(i,b)
        assert review.indian['cash_cents']==100100
        assert review.crypto['position_microcoin']==0
        assert review.crypto['cash_cents']==review.crypto['initial_cents']+review.crypto['realized_net_pnl_cents']


@pytest.mark.skipif(not ( __import__('pathlib').Path(__file__).resolve().parents[1] / 'tests' /
                          'test_stage95_fo_closed_trade_pipeline.py').is_file(),
                    reason='Exact Stage95 checkout required for full F&O/crypto integration')
def test_real_stage95_indian_account_and_crypto_restart_same_report(tmp_path):
    from pathlib import Path
    import runpy
    from nexus_titan.operations.stage96_accounting_review import selected_fo_scorecard
    from nexus_titan.operations.stage96_accounting_review import reconcile_fo_snapshot
    f=Path(__file__).resolve().parents[1] / 'tests' / 'test_stage95_fo_closed_trade_pipeline.py'
    h=runpy.run_path(str(f))
    env,pipeline=h['setup'](tmp_path)
    op,_=h['open_order'](env,pipeline)
    h['fill_order'](env,pipeline,op)
    h['fill_order'](env,pipeline,op,fill_id='fill-2')
    h['close_order'](env,pipeline,op.order_id)
    h['close_order'](env,pipeline,op.order_id,operation_id='close-2')
    reviewed=reconcile_fo_snapshot(pipeline.gateway.snapshot())
    key=b'k'*32
    book=CryptoPaperBook(path=tmp_path/'different-crypto.sqlite',account_id='crypto-a',
        limits=CryptoPaperLimits(200000,100000,150000,10000,paper_enabled=True),
        verification_key=key,indian_book_path=env['path'])
    state=book.snapshot()
    intent=CryptoPaperIntent('crypto-entry','BUY',5000,5000000,100)
    permit=seal_crypto_paper_permit(key,account_id=state.account_id,
        revision=state.journal_revision,tip=state.journal_tip,intent=intent,expires_epoch=105)
    book.apply(intent,permit,now_epoch=101,human_approved=True)
    review=read_only_dual_market_review(reviewed,book)
    assert review.indian['realized_net_pnl_cents'] != review.crypto['realized_net_pnl_cents']
    assert review.indian['currency']=='INR' and review.crypto['currency']=='USDT'
    assert review.crypto['position_microcoin']==5000
    assert not review.live_trading_enabled
