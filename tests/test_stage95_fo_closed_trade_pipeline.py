"""Actual ingested synthetic CSV -> signal/risk -> signed ledger -> closed P&L."""
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
import hashlib
import runpy
import sqlite3

import pytest

from nexus_titan.operations.fo_closed_trade_pipeline import FOClosedTradePipeline, PaperExecutionAssumptions, assess_fo_strategy
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.intelligence.pipeline import RiskRequest
from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskBlocked
from nexus_titan.operations.isolated_atomic_execution_book import Stage55SyntheticBookBlocked
from nexus_titan.operations.paper_controls import PaperAccess, PaperOperationBlocked
from nexus_titan.operations.synthetic_fo_execution import SyntheticFOExecutionGateway
from nexus_titan.operations.synthetic_option_positions import SyntheticCloseRequest

ROOT = Path(__file__).resolve().parents[1]
helper = runpy.run_path(str(ROOT/'tests/helpers/fo_synthetic_fixture.py'))


def assess(env, market, *, age=0, conflict=False):
    c=env['chains'][market]
    s=env['book'].snapshot_local_synthetic_portfolio()
    confirmation=SignalProposal('OPTIONS_CONFIRMATION','SELL' if conflict else 'BUY',
        'Explicit synthetic option confirmation, not calibrated alpha',c['72'].research_output_sha256,
        'Option evidence quality or risk veto fails')
    request=RiskRequest(s.initial_cents/100,5.50,5.0,c['75'].option_symbol,'BUY',c['contract'].lot_size,
                        current_exposure=(s.initial_cents-s.cash_cents+s.reserved_cents)/100,
                        current_open_positions=sum(o.open_quantity>0 or o.open_hold_cents>0 for o in s.orders))
    return assess_fo_strategy(boundary=env['boundary'],futures=c['futures'],aligned=c['71'],
                             options=c['72'],evolve=c['73'],confirmation=confirmation,
                             risk_request=request,now=datetime.fromtimestamp(env['clock'][0]+age,timezone.utc))


def setup(tmp_path, *, access=None, underlying='NIFTY', option_type='CE'):
    # Generate actual trending CSVs before the existing checksum/quality importer.
    # The importer still verifies the new declaration and every OHLCV row.
    source_globals=helper['chain_fixture'].__globals__
    original=source_globals['preflight_stage59_futures_csv']
    def trending(root, **args):
        path=root/args['declaration'].filename
        rows=path.read_text().splitlines()
        cols=rows[0].split(',');index=cols.index('close')
        direction=-1 if args['contract'].underlying==underlying and option_type=='PE' else 1
        for i in range(1,len(rows)):
            values=rows[i].split(',');values[index]=f'{100+direction*i*0.05:.2f}'
            values[cols.index('high')]='103.00';values[cols.index('low')]='97.00'
            rows[i]=','.join(values)
        raw=('\n'.join(rows)+'\n').encode();path.write_bytes(raw)
        args['declaration']=replace(args['declaration'],expected_sha256=hashlib.sha256(raw).hexdigest())
        return original(root,**args)
    with patch.dict(source_globals,preflight_stage59_futures_csv=trending):
        env = helper['environment'](tmp_path, history_bars=40, option_start_minute=35,
                                  lots=2, option_types={underlying: option_type})
    pipeline = FOClosedTradePipeline(SyntheticFOExecutionGateway(env['book']),
                                    boundary=env['boundary'], access=access or PaperAccess(True))
    return env, pipeline


def open_order(env, pipeline, market='NIFTY', oid='entry'):
    op = helper['opening'](env, oid, market)
    permit = helper['issue'](env, op)
    return op, pipeline.open(op, assessment=assess(env,market), risk_permit=permit, human_approved=True)


def fill_order(env, pipeline, op, *, qty=25, fill_id='fill-1'):
    price, fee, _ = pipeline.terms(symbol=op.symbol, side='BUY', quantity=qty,
                                 bid_cents=535, ask_cents=540)
    fill = SyntheticFOOperation('FILL',fill_id,op.order_id,quantity=qty,price_cents=price,fee_cents=fee)
    return pipeline.fill(fill,risk_permit=helper['issue'](env,fill),
                         bid_cents=535,ask_cents=540,available_quantity=qty,human_approved=True)


def close_order(env, pipeline, oid, *, qty=25, operation_id='close-1', bid=605):
    snapshot = pipeline.gateway.snapshot()
    pos = next(o for o in snapshot.orders if o.order_id==oid)
    price, fee, _ = pipeline.terms(symbol=pos.symbol,side='SELL',quantity=qty,
                                 bid_cents=bid,ask_cents=bid+5)
    request = SyntheticCloseRequest(operation_id,oid,pos.symbol,pos.contract_sha256,qty,price,fee)
    quote = env['authority'].issue_quote(env['boundary'],snapshot=snapshot,order_id=oid,
        quantity=qty,bid_cents=price,ask_cents=price+5,observed_epoch=env['clock'][0],
        estimated_exit_fee_cents=fee,now_epoch=env['clock'][0])
    authorization = env['authority'].issue_close(env['boundary'],request=request,snapshot=snapshot,
                                               quote=quote,now_epoch=env['clock'][0])
    return pipeline.close(request,authorization=authorization,bid_cents=bid,ask_cents=bid+5)


@pytest.mark.parametrize('market',['NIFTY','BANKNIFTY'])
@pytest.mark.parametrize('kind',['CE','PE'])
def test_closed_trade_complete_pipeline_partial_fills_charges_dashboard_and_restart(tmp_path,market,kind):
    env,pipeline=setup(tmp_path,underlying=market,option_type=kind)
    op,_=open_order(env,pipeline,market)
    fill_order(env,pipeline,op)
    fill_order(env,pipeline,op,fill_id='fill-2')
    one=close_order(env,pipeline,op.order_id)
    assert one.position_state=='PARTIALLY_CLOSED_LONG'
    two=close_order(env,pipeline,op.order_id,operation_id='close-2')
    assert two.position_state=='CLOSED_LONG'
    dashboard=pipeline.dashboard()
    s,p=dashboard['account'],dashboard['performance']
    assert p['closed_trade_count']==1 and p['filled_units']==50
    assert p['realized_net_pnl_cents']==50*(600-545)-p['execution_fees_cents']
    assert p['execution_fees_cents']>0 and s['remaining_cost_basis_cents']==0
    assert s['cash_cents']==s['initial_cents']+s['realized_net_pnl_cents']
    assert s['journal_revision']==p['journal_revision']==5
    assert s['journal_tip']==p['journal_sha256']
    assert not dashboard['live_trading_enabled'] and not dashboard['real_market_shadow_validated']
    env['book']=helper['reopen'](env)
    restarted=FOClosedTradePipeline(SyntheticFOExecutionGateway(env['book']),
                                   boundary=env['boundary'],access=PaperAccess(True))
    assert restarted.dashboard()==dashboard


@pytest.mark.parametrize('access,approval,auto',[
    (PaperAccess(),True,False),(PaperAccess(True),False,False),
    (PaperAccess(True),1,False),(PaperAccess(True),True,True),
    (PaperAccess(True,'RISKY'),False,True),
])
def test_denied_permission_never_reserves_capital(tmp_path,access,approval,auto):
    env,p=setup(tmp_path,access=access)
    op=helper['opening'](env)
    with pytest.raises(PaperOperationBlocked):
        p.open(op,assessment=assess(env,'NIFTY'),risk_permit=helper['issue'](env,op),
               human_approved=approval,autonomous=auto)
    assert p.gateway.snapshot().journal_revision==0


def test_risky_autonomous_still_needs_independent_permit(tmp_path):
    env,p=setup(tmp_path,access=PaperAccess(True,'RISKY',True,True))
    op=helper['opening'](env)
    with pytest.raises(Stage55SyntheticBookBlocked):
        p.open(op,assessment=assess(env,'NIFTY'),risk_permit=None,autonomous=True)
    p.open(op,assessment=assess(env,'NIFTY'),risk_permit=helper['issue'](env,op),autonomous=True)
    assert p.gateway.snapshot().journal_revision==1


@pytest.mark.parametrize('failure',['stale','conflicting_signal','tampered_source','missing_permit','expired_permit'])
def test_signal_data_and_independent_risk_fail_closed(tmp_path,failure):
    env,p=setup(tmp_path)
    op=helper['opening'](env)
    assessed=assess(env,'NIFTY',age=31 if failure=='stale' else 0,conflict=failure=='conflicting_signal')
    permit=helper['issue'](env,op)
    if failure=='tampered_source':assessed=replace(assessed,source_stage72_sha256='0'*64)
    if failure=='missing_permit':permit=None
    if failure=='expired_permit':env['clock'][0]+=11
    with pytest.raises(Stage55SyntheticBookBlocked):
        p.open(op,assessment=assessed,risk_permit=permit,human_approved=True)
    assert p.gateway.snapshot().journal_revision==0


def test_duplicate_fill_and_close_cannot_double_debit_or_credit(tmp_path):
    env,p=setup(tmp_path)
    op,_=open_order(env,p)
    receipt=fill_order(env,p,op)
    # The operation must remain byte-identical to the signed, committed economics.
    price,fee,_=p.terms(symbol=op.symbol,side='BUY',quantity=25,bid_cents=535,ask_cents=540)
    fill=SyntheticFOOperation('FILL','fill-1',op.order_id,quantity=25,price_cents=price,fee_cents=fee)
    replay=p.fill(fill,risk_permit=helper['issue'](env,fill),bid_cents=535,ask_cents=540,
                  available_quantity=25,human_approved=True)
    assert replay.replayed and replay.cash_cents==receipt.cash_cents
    p.cancel(SyntheticFOOperation('CANCEL','cancel-rest',op.order_id))
    close_order(env,p,op.order_id)
    before=p.dashboard()
    with pytest.raises(SyntheticFORiskBlocked):close_order(env,p,op.order_id,operation_id='over-close')
    assert p.dashboard()==before


def test_kill_stop_recovery_and_protective_reduce_only_exit(tmp_path):
    env,p=setup(tmp_path)
    op,_=open_order(env,p)
    fill_order(env,p,op)
    env['book'].set_local_synthetic_kill_switch(active=True,operation_id='emergency')
    with pytest.raises(SyntheticFORiskBlocked):fill_order(env,p,op,fill_id='after-stop')
    p.cancel(SyntheticFOOperation('CANCEL','cancel-rest',op.order_id))
    close_order(env,p,op.order_id)
    env['book']=helper['reopen'](env)
    assert env['book'].snapshot_local_synthetic_portfolio().kill_switch_active
    assert env['book'].snapshot_local_synthetic_portfolio().orders[0].open_quantity==0


@pytest.mark.parametrize('bid,ask',[(600,590),(1,5),(500,600),(True,540)])
def test_quote_spread_tick_and_type_rejections(tmp_path,bid,ask):
    env,p=setup(tmp_path)
    with pytest.raises(PaperOperationBlocked):
        p.terms(symbol='NIFTYOPT',side='BUY',quantity=25,bid_cents=bid,ask_cents=ask)


def test_missing_fee_or_wrong_execution_price_is_rejected(tmp_path):
    env,p=setup(tmp_path)
    op,_=open_order(env,p)
    fill=SyntheticFOOperation('FILL','free-fill',op.order_id,quantity=25,price_cents=545,fee_cents=0)
    with pytest.raises(PaperOperationBlocked,match='charges'):
        p.fill(fill,risk_permit=helper['issue'](env,fill),bid_cents=535,ask_cents=540,
               available_quantity=25,human_approved=True)
    assert p.gateway.snapshot().paid_notional_cents==0


def test_expired_contract_and_unsupported_futures_execution_stay_blocked(tmp_path):
    env,p=setup(tmp_path)
    with pytest.raises(SyntheticFORiskBlocked):
        p.terms(symbol='NIFTYFUT',side='BUY',quantity=25,bid_cents=535,ask_cents=540)
    env['clock'][0]=env['boundary'].instruments[0].expiry_epoch
    with pytest.raises(SyntheticFORiskBlocked,match='Stale|Expiry'):
        helper['issue'](env,helper['opening'](env))


def test_tampered_durable_ledger_is_not_reported_as_valid_dashboard(tmp_path):
    env,p=setup(tmp_path)
    op,_=open_order(env,p)
    fill_order(env,p,op)
    with sqlite3.connect(env['path']) as db:db.execute('UPDATE execution_events SET price_cents=999 WHERE kind="FILL"')
    with pytest.raises(Stage55SyntheticBookBlocked):p.dashboard()


@pytest.mark.parametrize('args',[(True,'SAFE',True,True),(True,'RISKY',True,False),(1,'SAFE',False,False)])
def test_invalid_policy_is_rejected(args):
    with pytest.raises(PaperOperationBlocked):PaperAccess(*args)


@pytest.mark.parametrize('available',[0,24,True,-1])
def test_partial_fill_liquidity_is_explicit_and_bounded(tmp_path,available):
    env,p=setup(tmp_path)
    op,_=open_order(env,p)
    price,fee,_=p.terms(symbol=op.symbol,side='BUY',quantity=25,bid_cents=535,ask_cents=540)
    fill=SyntheticFOOperation('FILL','illiquid',op.order_id,quantity=25,price_cents=price,fee_cents=fee)
    with pytest.raises(PaperOperationBlocked,match='liquidity'):
        p.fill(fill,risk_permit=helper['issue'](env,fill),bid_cents=535,ask_cents=540,
               available_quantity=available,human_approved=True)
    assert p.gateway.snapshot().paid_notional_cents==0
