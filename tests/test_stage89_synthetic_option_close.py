"""Actual synthetic CE/PE journal closing, signed evidence, P&L and MTM."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from threading import Barrier
import hashlib
import hmac
import json
import os
import runpy
import sqlite3

import pytest

from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskBlocked
from nexus_titan.operations.isolated_atomic_execution_book import Stage55SyntheticBookBlocked, _hash_event
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import inspect_stage76_fo_portfolio_risk
from nexus_titan.operations.stage83_fo_capital_reconciliation import inspect_stage83_fo_account_reconciliation
from nexus_titan.operations.synthetic_fo_execution import SyntheticFOExecutionGateway
from nexus_titan.operations.synthetic_option_positions import (
    SyntheticCloseRequest, SyntheticCloseAuthorization, SyntheticPositionBlocked,
)

ROOT=Path(__file__).resolve().parents[1]
helper=runpy.run_path(str(ROOT/'tests/helpers/fo_synthetic_fixture.py'))
environment,opening,issue,reopen=(helper[k] for k in ('environment','opening','issue','reopen'))


def setup(tmp_path,**kwargs):
    return environment(tmp_path,lots=2,option_types={'NIFTY':'CE','BANKNIFTY':'PE'},**kwargs)


def gateway(env):
    return SyntheticFOExecutionGateway(env['book'])


def enter(env,market='NIFTY',*,fills=None):
    op=opening(env,'entry-'+market,market)
    gateway(env).apply(op,risk_permit=issue(env,op))
    for i,(qty,price,fee) in enumerate(fills or [(op.quantity,550,10)]):
        fill=SyntheticFOOperation('FILL','fill-'+market+'-'+str(i),op.order_id,
                                  quantity=qty,price_cents=price,fee_cents=fee)
        gateway(env).apply(fill,risk_permit=issue(env,fill))
    return op.order_id


def position(env,oid):
    return next(p for p in gateway(env).snapshot().orders if p.order_id==oid)


def quote(env,oid,*,quantity=None,bid=600,fee=7,observed=None):
    snapshot=gateway(env).snapshot()
    p=next(p for p in snapshot.orders if p.order_id==oid)
    return env['authority'].issue_quote(env['boundary'],snapshot=snapshot,order_id=oid,
        quantity=p.open_quantity if quantity is None else quantity,bid_cents=bid,ask_cents=bid+5,
        observed_epoch=env['clock'][0] if observed is None else observed,
        estimated_exit_fee_cents=fee,now_epoch=env['clock'][0])


def request(env,oid,*,quantity=None,bid=600,fee=7,op='close-a'):
    p=position(env,oid)
    return SyntheticCloseRequest(op,oid,p.symbol,p.contract_sha256,
                                  p.open_quantity if quantity is None else quantity,bid,fee)


def authorize(env,r,q=None):
    return env['authority'].issue_close(env['boundary'],request=r,
        snapshot=gateway(env).snapshot(),quote=q or quote(env,r.order_id,quantity=r.quantity,
        bid=r.price_cents,fee=r.fee_cents),now_epoch=env['clock'][0])


def close(env,r,q=None):
    return gateway(env).close_position(r,authorization=authorize(env,r,q))


def check_conservation(s):
    assert s.initial_cents+s.exit_proceeds_cents == s.cash_cents+s.paid_notional_cents+s.paid_fees_cents
    assert s.cash_cents+s.remaining_cost_basis_cents == s.initial_cents+s.realized_net_pnl_cents
    assert s.available_cents == s.cash_cents-s.reserved_cents >= 0
    assert sum(p.open_hold_cents for p in s.orders) == s.reserved_cents
    assert sum(p.paid_fees_cents for p in s.orders) == s.paid_fees_cents
    for p in s.orders:
        assert p.open_quantity == p.filled_quantity-p.closed_quantity >= 0
        assert p.paid_notional_cents == p.remaining_premium_cents+sum(c.entry_premium_allocated_cents for c in p.closing_events)
        assert p.entry_fees_cents == p.remaining_entry_fees_cents+sum(c.entry_fees_allocated_cents for c in p.closing_events)


def resign(env,value,domain):
    data=json.dumps([domain,value.payload()],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return replace(value,signature_hex=hmac.new(env['key'],data,hashlib.sha256).hexdigest())


def test_ce_partial_close_weighted_cost_and_fee_rounding_are_conserved(tmp_path):
    env=setup(tmp_path)
    oid=enter(env,fills=[(25,545,5),(25,550,8)])
    assert position(env,oid).option_type=='CE'
    before=gateway(env).performance_report()
    assert before.realized_net_pnl_cents==0 and before.net_pnl_cents is None
    first=close(env,request(env,oid,quantity=25))
    c=first.close_accounting
    assert (c.entry_premium_allocated_cents,c.entry_fees_allocated_cents)==(13687,6)
    assert (c.exit_proceeds_cents,c.exit_fees_cents)==(15000,7)
    assert (c.gross_realized_pnl_cents,c.net_realized_pnl_cents)==(1313,1300)
    assert (c.remaining_premium_cents,c.remaining_entry_fees_cents)==(13688,7)
    assert first.position_state=='PARTIALLY_CLOSED_LONG'
    assert gateway(env).performance_report().closed_trade_count==0
    final=close(env,request(env,oid,quantity=25,bid=500,fee=3,op='close-last'))
    assert final.position_state=='CLOSED_LONG'
    assert final.close_accounting.net_realized_pnl_cents==-1198
    report=gateway(env).performance_report()
    assert (report.gross_realized_pnl_cents,report.realized_net_pnl_cents)==(125,102)
    assert report.execution_fees_cents==23
    assert report.closed_trade_count==report.win_count==1 and report.loss_count==0
    assert report.net_pnl_cents==102 and report.current_synthetic_equity_cents==env['book'].starting_cents+102
    assert report.profit_factor is report.expectancy_cents is report.max_drawdown_percent is None
    check_conservation(gateway(env).snapshot())


def test_banknifty_pe_full_close_is_long_only_and_profitable_cash_can_exceed_initial(tmp_path):
    env=setup(tmp_path)
    oid=enter(env,'BANKNIFTY')
    assert position(env,oid).option_type=='PE'
    result=close(env,request(env,oid,bid=650,fee=12))
    assert result.position_state=='CLOSED_LONG'
    assert result.close_accounting.net_realized_pnl_cents==4978
    assert result.cash_cents==env['book'].starting_cents+4978
    assert result.trading_authority is False and result.live_orders_transmitted==0
    with pytest.raises(SyntheticPositionBlocked,match='held long units'):
        authorize(env,request(env,oid,quantity=25,op='short-attempt'))
    check_conservation(gateway(env).snapshot())


@pytest.mark.parametrize('bad',['over-close','unknown-position','cross-contract','partial-odd-lot','off-tick'])
def test_invalid_close_is_denied_by_issuer_and_book_even_with_faulty_signed_evidence(tmp_path,bad):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    auth=authorize(env,r)
    if bad=='over-close': r=replace(r,quantity=75)
    elif bad=='unknown-position': r=replace(r,order_id='absent')
    elif bad=='cross-contract':
        bank=env['boundary'].position_contract('BANKNIFTYOPT')
        r=replace(r,symbol='BANKNIFTYOPT',contract_sha256=bank['contract_sha256'])
    elif bad=='partial-odd-lot': r=replace(r,quantity=5)
    else: r=replace(r,price_cents=601)
    with pytest.raises(SyntheticFORiskBlocked):
        authorize(env,r,auth.quote)
    # A privileged but faulty issuer is not allowed to bypass the ledger's
    # independent long quantity / lot / contract checks.
    q=resign(env,replace(auth.quote,order_id=r.order_id,symbol=r.symbol,
        contract_sha256=r.contract_sha256,quantity=r.quantity,
        bid_cents=r.price_cents,ask_cents=r.price_cents+5),'STAGE89_QUOTE_V1')
    forged=resign(env,replace(auth,request_sha256=r.digest,quote=q),'STAGE89_CLOSE_V1')
    before=gateway(env).snapshot()
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway(env).close_position(r,authorization=forged)
    assert gateway(env).snapshot()==before


def test_pending_entry_must_be_cancelled_and_full_odd_lot_residual_may_be_closed(tmp_path):
    env=setup(tmp_path)
    oid=enter(env,fills=[(10,550,3)])
    r=request(env,oid,quantity=10,fee=2)
    with pytest.raises(SyntheticPositionBlocked,match='Cancel pending'):
        authorize(env,r)
    gateway(env).apply(SyntheticFOOperation('CANCEL','cancel-rest',oid))
    result=close(env,r)
    assert result.position_state=='CLOSED_LONG' and result.close_accounting.quantity==10
    check_conservation(gateway(env).snapshot())


def test_exact_authenticated_close_retry_after_expiry_and_restart_never_pays_twice(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    auth=authorize(env,r)
    original=gateway(env).close_position(r,authorization=auth)
    before=gateway(env).snapshot()
    env['clock'][0]+=60
    env['book']=reopen(env)
    retry=gateway(env).close_position(r,authorization=auth)
    assert retry.replayed and retry.close_accounting==original.close_accounting
    assert gateway(env).snapshot()==before
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway(env).close_position(r,authorization=None)
    with pytest.raises(Stage55SyntheticBookBlocked,match='conflicts'):
        gateway(env).close_position(replace(r,fee_cents=r.fee_cents+1),authorization=auth)


@pytest.mark.parametrize('identical',[False,True])
def test_concurrent_close_requests_cannot_produce_negative_holdings_or_double_proceeds(tmp_path,identical):
    env=setup(tmp_path)
    oid=enter(env)
    requests=[request(env,oid,op='close-a' if identical else 'close-'+str(i)) for i in range(2)]
    auths=[authorize(env,r) for r in requests]
    barrier=Barrier(2)
    def submit(i):
        barrier.wait(timeout=5)
        try: return gateway(env).close_position(requests[i],authorization=auths[i])
        except Stage55SyntheticBookBlocked: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,range(2)))
    assert sum(r is not None and not r.replayed for r in results)==1
    assert sum(r is not None for r in results)==(2 if identical else 1)
    s=gateway(env).snapshot()
    assert s.journal_revision==3 and s.exit_proceeds_cents==30000
    assert s.orders[0].open_quantity==0
    check_conservation(s)


@pytest.mark.parametrize('damage',['missing','entry-permit','signature','request','scope','risk-revision','expired','future','quote-tamper'])
def test_close_authorization_is_default_deny_without_any_economic_mutation(tmp_path,damage):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    a=authorize(env,r)
    if damage=='missing': a=None
    elif damage=='entry-permit': a=issue(env,opening(env,'other','BANKNIFTY'))
    elif damage=='signature': a=replace(a,signature_hex='0'*64)
    elif damage=='request': a=replace(a,request_sha256='0'*64)
    elif damage=='scope': a=replace(a,ledger_scope_sha256='0'*64)
    elif damage=='risk-revision': a=replace(a,risk_revision=a.risk_revision+1)
    elif damage=='expired': env['clock'][0]+=10
    elif damage=='future': env['clock'][0]-=1
    else: a=replace(a,quote=replace(a.quote,bid_cents=595))
    before=gateway(env).snapshot()
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway(env).close_position(r,authorization=a)
    assert gateway(env).snapshot()==before


def test_stale_head_permit_and_close_authorization_cannot_open_exposure(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    a=authorize(env,r)
    other=opening(env,'bank-entry','BANKNIFTY')
    with pytest.raises(Stage55SyntheticBookBlocked,match='risk permit'):
        gateway(env).apply(other,risk_permit=a)
    gateway(env).apply(other,risk_permit=issue(env,other))
    with pytest.raises(Stage55SyntheticBookBlocked,match='Stale'):
        gateway(env).close_position(r,authorization=a)


def test_kill_blocks_entries_and_fills_but_allows_fresh_authorized_protective_close(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    old=authorize(env,r)
    bank=opening(env,'bank','BANKNIFTY')
    entry_permit=issue(env,bank)
    env['book'].set_local_synthetic_kill_switch(active=True,operation_id='kill')
    with pytest.raises(Stage55SyntheticBookBlocked,match='kill switch'):
        gateway(env).apply(bank,risk_permit=entry_permit)
    with pytest.raises(Stage55SyntheticBookBlocked,match='Stale'):
        gateway(env).close_position(r,authorization=old)
    result=close(env,r)
    assert result.position_state=='CLOSED_LONG'
    assert gateway(env).snapshot().kill_switch_active
    with pytest.raises(Stage55SyntheticBookBlocked,match='rearmed'):
        env['book'].set_local_synthetic_kill_switch(active=False,operation_id='bypass')


def test_closing_uses_fresh_exit_evidence_even_when_old_entry_research_is_stale(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    env['clock'][0]+=61
    with pytest.raises(SyntheticFORiskBlocked,match='Stale'):
        issue(env,opening(env,'bank','BANKNIFTY'))
    result=close(env,request(env,oid))
    assert result.position_state=='CLOSED_LONG'


def test_closed_profit_does_not_replenish_original_entry_allocation(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    close(env,request(env,oid))
    again=opening(env,'recycle-profit')
    with pytest.raises(Stage55SyntheticBookBlocked,match='allocation already committed'):
        gateway(env).apply(again,risk_permit=issue(env,again))


def test_locally_realized_loss_cannot_be_hidden_by_healthy_entry_telemetry(tmp_path):
    env=setup(tmp_path,capital=800000)
    oid=enter(env)
    close(env,request(env,oid,bid=5,fee=7))
    assert gateway(env).snapshot().realized_net_pnl_cents < -24000
    bank=opening(env,'bank','BANKNIFTY')
    permit=issue(env,bank)  # Privileged test telemetry still claims zero loss.
    with pytest.raises(Stage55SyntheticBookBlocked,match='realized session loss'):
        gateway(env).apply(bank,risk_permit=permit)


def test_mtm_and_realized_pnl_are_separate_and_valuation_is_read_only(tmp_path):
    env=setup(tmp_path)
    oid=enter(env,fills=[(25,545,5),(25,550,8)])
    close(env,request(env,oid,quantity=25))
    before=gateway(env).snapshot()
    up=gateway(env).mark_to_market((quote(env,oid,bid=650,fee=5),))
    down=gateway(env).mark_to_market((quote(env,oid,bid=450,fee=5),))
    assert up.realized_net_pnl_cents==down.realized_net_pnl_cents==1300
    assert up.remaining_cost_basis_cents==13695
    assert up.unrealized_gross_pnl_cents==16250-13688
    assert up.unrealized_net_pnl_cents==16250-13695-5
    assert down.unrealized_net_pnl_cents==11250-13695-5
    assert up.total_hypothetical_equity_cents==before.initial_cents+1300+up.unrealized_net_pnl_cents
    assert up.total_hypothetical_equity_cents-down.total_hypothetical_equity_cents==5000
    assert gateway(env).snapshot()==before
    assert up.synthetic_only and not up.market_evidence_verified and not up.live_trading_enabled
    report=gateway(env).performance_report(quotes=(quote(env,oid,bid=650,fee=5),))
    assert report.realized_net_pnl_cents==1300 and report.closed_trade_count==0
    assert report.open_unrealized_pnl_cents==up.unrealized_net_pnl_cents
    assert report.current_synthetic_equity_cents==up.total_hypothetical_equity_cents
    assert gateway(env).performance_report().current_synthetic_equity_cents is None


@pytest.mark.parametrize('bad',['stale','future','corrupt-price','unsigned','unknown-contract','wrong-quantity','duplicate','missing'])
def test_invalid_mtm_evidence_never_changes_cash_or_realizes_profit(tmp_path,bad):
    env=setup(tmp_path)
    oid=enter(env)
    q=quote(env,oid)
    quotes=(q,)
    if bad=='stale': env['clock'][0]+=31
    elif bad=='future': q=resign(env,replace(q,observed_epoch=q.observed_epoch+1),'STAGE89_QUOTE_V1'); quotes=(q,)
    elif bad=='corrupt-price': quotes=(replace(q,bid_cents=595),)
    elif bad=='unsigned': quotes=(replace(q,signature_hex=''),)
    elif bad=='unknown-contract': quotes=(replace(q,contract_sha256='0'*64),)
    elif bad=='wrong-quantity': quotes=(resign(env,replace(q,quantity=25),'STAGE89_QUOTE_V1'),)
    elif bad=='duplicate': quotes=(q,q)
    else: quotes=()
    before=gateway(env).snapshot()
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway(env).mark_to_market(quotes)
    assert gateway(env).snapshot()==before


def test_combined_ce_pe_reporting_requires_synchronized_quotes_and_reconciles_one_account(tmp_path):
    env=setup(tmp_path)
    n,b=enter(env),enter(env,'BANKNIFTY')
    close(env,request(env,n,quantity=25))
    close(env,request(env,b,bid=500,fee=10,op='close-bank'))
    env['clock'][0]+=1
    q=quote(env,n,bid=575,fee=4)
    report=gateway(env).performance_report(quotes=(q,))
    assert report.closed_trade_count==report.loss_count==1 and report.win_count==0
    assert report.realized_net_pnl_cents==1238-2520  # NIFTY: 15000-13750-5-7; BANK: 25000-27500-10-10.
    research=inspect_stage76_fo_portfolio_risk(packets=env['boundary'].packets,
                policy=env['boundary'].policy,telemetry=env['telemetry'])
    reconciliation=inspect_stage83_fo_account_reconciliation(env['book'],research)
    assert reconciliation.local_single_book_reconciliation_consistent
    assert report.journal_sha256==reconciliation.journal_sha256
    check_conservation(gateway(env).snapshot())
    # A separate still-open pair exercises portfolio quote timestamp coherence.
    other=setup(tmp_path/'pair')
    x,y=enter(other),enter(other,'BANKNIFTY')
    qx=quote(other,x)
    other['clock'][0]+=1
    qy=quote(other,y)
    with pytest.raises(Stage55SyntheticBookBlocked,match='synchronized'):
        gateway(other).mark_to_market((qx,qy))


def test_reserved_capital_is_not_subtracted_twice_from_equity_and_flat_trade_counts_are_auditable(tmp_path):
    env=setup(tmp_path)
    n=enter(env,fills=[(50,550,0)])
    bank=opening(env,'pending-bank','BANKNIFTY')
    gateway(env).apply(bank,risk_permit=issue(env,bank))
    close(env,request(env,n,bid=550,fee=0))
    mtm=gateway(env).mark_to_market(())
    report=gateway(env).performance_report()
    assert mtm.total_hypothetical_equity_cents==env['book'].starting_cents
    assert mtm.reserved_capital_cents>0 and mtm.available_cash_cents==mtm.total_hypothetical_equity_cents-mtm.reserved_capital_cents
    assert report.closed_trade_count==report.breakeven_count==1
    assert report.win_count==report.loss_count==0


@pytest.mark.parametrize('point',['before-event','after-proof-before-head'])
def test_close_transaction_rollback_keeps_cash_holdings_pnl_and_proofs_unchanged(tmp_path,monkeypatch,point):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    a=authorize(env,r)
    g=gateway(env); before=g.snapshot()
    if point=='before-event':
        def fail(*_): raise RuntimeError('crash')
        monkeypatch.setattr(env['book'],'_write_event',fail)
    else:
        original,count=env['book']._derive,[0]
        def fail(conn):
            count[0]+=1
            if count[0]==2: raise RuntimeError('crash')
            return original(conn)
        monkeypatch.setattr(env['book'],'_derive',fail)
    with pytest.raises(RuntimeError,match='crash'):
        g.close_position(r,authorization=a)
    monkeypatch.undo()
    env['book']=reopen(env)
    assert gateway(env).snapshot()==before
    with sqlite3.connect(env['path']) as db:
        assert db.execute("SELECT count(*) FROM execution_events WHERE kind='CLOSE'").fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM execution_fo_permits').fetchone()[0]==2
    gateway(env).close_position(r,authorization=a)
    check_conservation(gateway(env).snapshot())


@pytest.mark.skipif(not hasattr(os,'fork'),reason='Abrupt process death requires POSIX')
@pytest.mark.parametrize('point',['before-commit','after-commit-before-response'])
def test_real_process_death_and_restart_never_duplicate_close_proceeds(tmp_path,point):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid); a=authorize(env,r)
    g=gateway(env); before=g.snapshot()
    pid=os.fork()
    if pid==0:
        try:
            if point=='before-commit':
                original=env['book']._write_event
                def die(*args): original(*args); os._exit(73)
                env['book']._write_event=die
            g.close_position(r,authorization=a)
            os._exit(73)
        except BaseException:
            os._exit(91)
    _,status=os.waitpid(pid,0)
    assert os.waitstatus_to_exitcode(status)==73
    env['book']=reopen(env)
    snap=gateway(env).snapshot()
    assert snap.journal_revision==before.journal_revision+(point!='before-commit')
    receipt=gateway(env).close_position(r,authorization=a)
    assert receipt.replayed is (point!='before-commit')
    assert gateway(env).snapshot().exit_proceeds_cents==30000
    assert gateway(env).snapshot().journal_revision==3
    check_conservation(gateway(env).snapshot())


@pytest.mark.parametrize('damage',['rehash-price','signature','missing-proof','head-cash'])
def test_corrupted_close_journal_or_rewritten_economics_fail_replay(tmp_path,damage):
    env=setup(tmp_path)
    oid=enter(env)
    close(env,request(env,oid))
    with sqlite3.connect(env['path']) as db:
        if damage=='rehash-price':
            row=list(db.execute("SELECT * FROM execution_events WHERE kind='CLOSE'").fetchone())
            row[6]+=5
            hashed=_hash_event(tuple(row[:-1]))
            db.execute("UPDATE execution_events SET price_cents=?,event_sha=? WHERE kind='CLOSE'",(row[6],hashed))
            db.execute('UPDATE execution_head SET cash_cents=cash_cents+?,event_sha=?',(row[5]*5,hashed))
        elif damage=='signature':
            raw=db.execute('SELECT permit_json FROM execution_fo_permits WHERE seq=3').fetchone()[0]
            a=SyntheticCloseAuthorization.decode(raw)
            db.execute('UPDATE execution_fo_permits SET permit_json=? WHERE seq=3',(replace(a,signature_hex='0'*64).encode(),))
        elif damage=='missing-proof': db.execute('DELETE FROM execution_fo_permits WHERE seq=3')
        else: db.execute('UPDATE execution_head SET cash_cents=cash_cents+1')
    assert not env['book'].inspect().local_integrity_verified
    with pytest.raises((Stage55SyntheticBookBlocked,SyntheticFORiskBlocked)):
        reopen(env)


@pytest.mark.parametrize('rollback',[False,True])
def test_verified_stage88_schema_upgrade_preserves_history_and_is_atomic(tmp_path,monkeypatch,rollback):
    env=setup(tmp_path)
    oid=enter(env)
    before=gateway(env).snapshot()
    with sqlite3.connect(env['path']) as db:
        schema=db.execute("SELECT sql FROM sqlite_master WHERE name='execution_events'").fetchone()[0]
        old=schema.replace('execution_events','old_events_stage88',1).replace(",'CLOSE'",'')
        db.execute(old)
        db.execute('INSERT INTO old_events_stage88 SELECT * FROM execution_events')
        db.execute('DROP TABLE execution_events')
        db.execute('ALTER TABLE old_events_stage88 RENAME TO execution_events')
    if rollback:
        cls=type(env['book']); original=cls._upgrade_close_schema
        def fail(self,conn): original(self,conn); raise RuntimeError('migration-crash')
        monkeypatch.setattr(cls,'_upgrade_close_schema',fail)
        with pytest.raises(RuntimeError): reopen(env)
        monkeypatch.undo()
        with sqlite3.connect(env['path']) as db:
            assert "'CLOSE'" not in db.execute("SELECT sql FROM sqlite_master WHERE name='execution_events'").fetchone()[0]
    env['book']=reopen(env)
    assert gateway(env).snapshot()==before
    close(env,request(env,oid))
    check_conservation(gateway(env).snapshot())


def test_expiry_and_negative_or_false_real_market_claims_fail_closed(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    q=quote(env,oid)
    for change in ({'bid_cents':-1},{'quantity':True},{'market_evidence_verified':True},{'synthetic_only':False}):
        with pytest.raises(SyntheticPositionBlocked): replace(q,**change)
    with pytest.raises(SyntheticPositionBlocked): replace(request(env,oid),side='SELL_SHORT')
    env['clock'][0]=env['boundary'].instruments[0].expiry_epoch
    with pytest.raises(SyntheticPositionBlocked,match='expired'):
        quote(env,oid)


@pytest.mark.parametrize('market',['NIFTY','BANKNIFTY'])
@pytest.mark.parametrize('option_type',['CE','PE'])
def test_each_supported_underlying_and_option_side_uses_its_pinned_contract(tmp_path,market,option_type):
    env=environment(tmp_path,lots=2,option_types={market:option_type})
    oid=enter(env,market)
    p=position(env,oid)
    assert p.option_type==option_type
    r=request(env,oid,quantity=25 if option_type=='CE' else 50)
    result=close(env,r)
    assert result.close_accounting.quantity==r.quantity
    assert position(env,oid).open_quantity==50-r.quantity
    check_conservation(gateway(env).snapshot())


@pytest.mark.parametrize('change',[{'price_cents':590},{'price_cents':610},{'fee_cents':8}])
def test_close_requires_exact_signed_bid_and_bounded_actual_exit_fee(tmp_path,change):
    env=setup(tmp_path)
    oid=enter(env)
    original=request(env,oid)
    valid=authorize(env,original)
    invalid=replace(original,**change)
    with pytest.raises(SyntheticPositionBlocked,match='economics'):
        authorize(env,invalid,valid.quote)
    faulty=resign(env,replace(valid,request_sha256=invalid.digest),'STAGE89_CLOSE_V1')
    with pytest.raises(Stage55SyntheticBookBlocked,match='economics'):
        gateway(env).close_position(invalid,authorization=faulty)
    assert position(env,oid).open_quantity==50


def test_fresh_authorization_cannot_relabel_an_old_quote_as_fresh(tmp_path):
    env=setup(tmp_path)
    oid=enter(env)
    r=request(env,oid)
    old=authorize(env,r)
    env['clock'][0]+=31
    faulty=resign(env,replace(old,issued_epoch=env['clock'][0],expires_epoch=env['clock'][0]+10),'STAGE89_CLOSE_V1')
    with pytest.raises(Stage55SyntheticBookBlocked,match='Stale'):
        gateway(env).close_position(r,authorization=faulty)
    assert position(env,oid).open_quantity==50


def test_custom_legacy_indexes_are_not_silently_destroyed_by_schema_upgrade(tmp_path):
    env=setup(tmp_path)
    enter(env)
    with sqlite3.connect(env['path']) as db:
        schema=db.execute("SELECT sql FROM sqlite_master WHERE name='execution_events'").fetchone()[0]
        db.execute(schema.replace('execution_events','old_stage88',1).replace(",'CLOSE'",''))
        db.execute('INSERT INTO old_stage88 SELECT * FROM execution_events')
        db.execute('DROP TABLE execution_events')
        db.execute('ALTER TABLE old_stage88 RENAME TO execution_events')
        db.execute('CREATE INDEX external_review_index ON execution_events(symbol)')
    with pytest.raises(Stage55SyntheticBookBlocked,match='reviewed migration'):
        reopen(env)
    with sqlite3.connect(env['path']) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='external_review_index'").fetchone()
        assert db.execute('SELECT revision FROM execution_head').fetchone()[0]==2
