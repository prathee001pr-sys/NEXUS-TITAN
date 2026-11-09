from dataclasses import replace,asdict
import sqlite3,os
import pytest
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBlocked,CryptoPaperLimits,CryptoPaperBook,CryptoPaperIntent,
    seal_crypto_paper_permit)
KEY=b'\x9a'*32

def config(**kw):
    return CryptoPaperLimits(**({'initial_cash_cents':200000,'max_order_cents':100000,
        'max_exposure_cents':150000,'max_session_loss_cents':10000,
        'paper_enabled':True}|kw))

def book(tmp_path,**kw):
    return CryptoPaperBook(path=tmp_path/'crypto.sqlite',account_id='crypto-a',limits=config(**kw),verification_key=KEY)

def trade(b,side,qty,oid,*,price=5000000,epoch=100,approval=True,autonomous=False):
    s=b.snapshot();i=CryptoPaperIntent(oid,side,qty,price,epoch)
    p=seal_crypto_paper_permit(KEY,account_id=b.account_id,revision=s.journal_revision,
                               tip=s.journal_tip,intent=i,expires_epoch=epoch+10)
    return b.apply(i,p,now_epoch=epoch+1,human_approved=approval,autonomous=autonomous)

def test_buy_partial_sell_restart_and_full_close(tmp_path):
    b=book(tmp_path)
    s,replay=trade(b,'BUY',20000,'buy-1')
    assert not replay and (s.position_microcoin,s.remaining_cost_basis_cents)==(20000,100100)
    s,_=trade(b,'SELL',8000,'sell-1',price=6000000,epoch=101)
    assert s.position_microcoin==12000 and s.realized_net_pnl_cents>0
    s,_=trade(b,'SELL',12000,'sell-2',price=6000000,epoch=102)
    assert s.position_microcoin==0 and s.remaining_cost_basis_cents==0
    assert s.cash_cents==s.initial_cents+s.realized_net_pnl_cents
    reopened=book(tmp_path)
    assert reopened.snapshot()==s
    assert not reopened.snapshot().live_trading_enabled

def test_duplicate_ack_after_commit_and_conflict(tmp_path):
    b=book(tmp_path)
    i=CryptoPaperIntent('dup','BUY',10000,5000000,100)
    old=b.snapshot();p=seal_crypto_paper_permit(KEY,account_id=b.account_id,
        revision=old.journal_revision,tip=old.journal_tip,intent=i,expires_epoch=111)
    s,was=b.apply(i,p,now_epoch=101,human_approved=True)
    same,was=b.apply(i,p,now_epoch=150,human_approved=True)
    assert same==s and was
    with pytest.raises(CryptoPaperBlocked):b.apply(replace(i,price_cents_per_coin=6000000),p,now_epoch=150,human_approved=True)

@pytest.mark.parametrize('kind', ['missing','forged','stale','future','unapproved','autonomous_safe'])
def test_authority_blocks_unsafe_buy(tmp_path,kind):
    b=book(tmp_path)
    s=b.snapshot();i=CryptoPaperIntent('entry','BUY',5000,5000000,100)
    p=seal_crypto_paper_permit(KEY,account_id=b.account_id,revision=0,tip=s.journal_tip,intent=i,expires_epoch=110)
    if kind=='missing':p=None
    if kind=='forged':p=replace(p,signature_hex='0'*64)
    if kind=='stale':i=replace(i,observed_epoch=1)
    if kind=='future':i=replace(i,observed_epoch=200)
    with pytest.raises(CryptoPaperBlocked):
        b.apply(i,p,now_epoch=101,human_approved=kind not in ('unapproved','autonomous_safe'),
                autonomous=kind=='autonomous_safe')
    assert b.snapshot().journal_revision==0

@pytest.mark.parametrize('qty,price',[(1000000,5000000),(1,1),(0,100),(True,5000000)])
def test_caps_invalid_or_expensive(tmp_path,qty,price):
    b=book(tmp_path)
    if type(qty) is not int or qty==0:
        with pytest.raises(CryptoPaperBlocked):CryptoPaperIntent('e','BUY',qty,price,100)
    else:
        with pytest.raises(CryptoPaperBlocked):trade(b,'BUY',qty,'exp',price=price) if qty>100000 else trade(b,'SELL',qty,'short',price=price)


def test_kill_prevents_new_buy_but_allows_protective_sell(tmp_path):
    b=book(tmp_path)
    trade(b,'BUY',10000,'buy')
    b.stop('kill-switch')
    with pytest.raises(CryptoPaperBlocked):trade(b,'BUY',1000,'no-more',epoch=101)
    s,_=trade(b,'SELL',10000,'protective',epoch=101)
    assert s.position_microcoin==0 and s.kill_active
    assert book(tmp_path).snapshot()==s


def test_separate_ledger_and_policy_immutability(tmp_path):
    p=tmp_path/'crypto.sqlite'
    with pytest.raises(CryptoPaperBlocked):CryptoPaperBook(path=p,account_id='crypto-a',limits=config(),verification_key=KEY,indian_book_path=p)
    b=book(tmp_path)
    with pytest.raises(CryptoPaperBlocked):CryptoPaperBook(path=p,account_id='other',limits=config(),verification_key=KEY)
    with pytest.raises(CryptoPaperBlocked):CryptoPaperBook(path=p,account_id='crypto-a',limits=config(fee_bps=7),verification_key=KEY)


def test_tamper_detected(tmp_path):
    b=book(tmp_path)
    trade(b,'BUY',10000,'entry')
    with sqlite3.connect(tmp_path/'crypto.sqlite') as db:
        db.execute("UPDATE crypto_events SET payload='{}' WHERE seq=1")
    with pytest.raises(CryptoPaperBlocked):b.snapshot()


def test_equity_mark_is_synthetic_only(tmp_path):
    b=book(tmp_path)
    trade(b,'BUY',10000,'entry')
    x=b.equity_at_synthetic_bid(price_cents_per_coin=5100000,observed_epoch=101,now_epoch=102)
    assert x['market']=='CRYPTO_PAPER' and x['currency']=='USDT'
    assert x['synthetic_equity_cents']<b.snapshot().cash_cents+51000
    assert not x['real_market_evidence_verified'] and not x['live_trading_enabled']
    with pytest.raises(CryptoPaperBlocked):b.equity_at_synthetic_bid(price_cents_per_coin=5100000,observed_epoch=1,now_epoch=102)


def test_disabled_by_default(tmp_path):
    b=book(tmp_path,paper_enabled=False)
    with pytest.raises(CryptoPaperBlocked):trade(b,'BUY',10000,'deny')


def test_risky_requires_explicit_allowance(tmp_path):
    b=book(tmp_path,mode='RISKY',autonomy_enabled=True)
    s,_=trade(b,'BUY',10000,'auto',approval=False,autonomous=True)
    assert s.position_microcoin==10000


def test_atomic_fence_rejects_stale_distinct_permits(tmp_path):
    b=book(tmp_path)
    old=b.snapshot()
    one=CryptoPaperIntent('a','BUY',5000,5000000,100)
    two=CryptoPaperIntent('b','BUY',5000,5000000,100)
    permits=[seal_crypto_paper_permit(KEY,account_id=b.account_id,
        revision=old.journal_revision,tip=old.journal_tip,intent=i,expires_epoch=110)
        for i in (one,two)]
    b.apply(one,permits[0],now_epoch=101,human_approved=True)
    with pytest.raises(CryptoPaperBlocked,match='Stale'):
        b.apply(two,permits[1],now_epoch=101,human_approved=True)
    assert b.snapshot().journal_revision==1


def test_two_threads_cannot_double_admit_with_same_head(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    b=book(tmp_path)
    old=b.snapshot()
    intents=[CryptoPaperIntent(f'trade{i}','BUY',5000,5000000,100) for i in range(2)]
    permits=[seal_crypto_paper_permit(KEY,account_id=b.account_id,
        revision=old.journal_revision,tip=old.journal_tip,intent=i,expires_epoch=110) for i in intents]
    def run(i):
        try:
            b.apply(intents[i],permits[i],now_epoch=101,human_approved=True)
            return 'COMMIT'
        except CryptoPaperBlocked:
            return 'DENIED'
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(run,range(2)))
    assert sorted(results)==['COMMIT','DENIED']
    assert b.snapshot().journal_revision==1


def test_atomic_failure_does_not_append_event(tmp_path):
    b=book(tmp_path)
    with pytest.raises(CryptoPaperBlocked):trade(b,'BUY',1000000,'too-big')
    assert b.snapshot().journal_revision==0


def test_new_trade_after_restarted_process_requires_fresh_head_permit(tmp_path):
    b=book(tmp_path)
    state=b.snapshot()
    initial=CryptoPaperIntent('old','BUY',10000,5000000,100)
    oldpermit=seal_crypto_paper_permit(KEY,account_id=b.account_id,
        revision=state.journal_revision,tip=state.journal_tip,intent=initial,expires_epoch=110)
    b.apply(initial,oldpermit,now_epoch=101,human_approved=True)
    restarted=book(tmp_path)
    stale=CryptoPaperIntent('new','BUY',10000,5000000,101)
    wrong=seal_crypto_paper_permit(KEY,account_id=b.account_id,
        revision=state.journal_revision,tip=state.journal_tip,intent=stale,expires_epoch=111)
    with pytest.raises(CryptoPaperBlocked):
        restarted.apply(stale,wrong,now_epoch=102,human_approved=True)
    state2,_=trade(restarted,'BUY',10000,'new',epoch=101)
    assert state2.journal_revision==2
