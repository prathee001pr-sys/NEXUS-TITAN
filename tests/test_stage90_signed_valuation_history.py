"""Stage90 tests: historical synthetic quote provenance and conservative metric gates."""
from dataclasses import replace
from pathlib import Path
import runpy

import pytest

from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation
from nexus_titan.operations.stage90_signed_valuation_history import (
    Stage90HistoryBlocked, capture_stage90_checkpoint, inspect_stage90_history,
)

ROOT=Path(__file__).resolve().parents[1]
fixture=runpy.run_path(str(ROOT/'tests/helpers/fo_synthetic_fixture.py'))
environment,opening,issue=(fixture[k] for k in ('environment','opening','issue'))


def setup_account(tmp_path, *, filled=True):
    env=environment(tmp_path,lots=1)
    if filled:
        op=opening(env,'stage90-order','NIFTY')
        env['book'].reserve_synthetic_buy(
            request_id=op.operation_id,symbol=op.symbol,quantity=op.quantity,
            limit_price_cents=op.price_cents,fee_buffer_cents=op.fee_buffer_cents,
            risk_permit=issue(env,op))
        fill=SyntheticFOOperation(
            'FILL','stage90-fill',op.order_id,quantity=op.quantity,
            price_cents=550,fee_cents=10)
        env['book'].record_simulated_fill(
            order_id=op.order_id,fill_id=fill.operation_id,quantity=fill.quantity,
            price_cents=fill.price_cents,fee_cents=fill.fee_cents,
            risk_permit=issue(env,fill),evidence_source='LOCAL_SYNTHETIC_TEST_ONLY')
        env['order_id']=op.order_id
    return env


def checkpoint(env,*,bid=600,previous=None,empty=False):
    env['clock'][0]+=1
    quotes=()
    if not empty:
        s=env['book'].snapshot_local_synthetic_portfolio()
        p=next(o for o in s.orders if o.order_id==env['order_id'])
        quotes=(env['authority'].issue_quote(
            env['boundary'],snapshot=s,order_id=p.order_id,
            quantity=p.open_quantity,bid_cents=bid,ask_cents=bid+5,
            observed_epoch=env['clock'][0],estimated_exit_fee_cents=7,
            now_epoch=env['clock'][0]),)
    return capture_stage90_checkpoint(
        env['book'],env['boundary'],issuer_key=env['key'],
        quotes=quotes,previous=previous)


def sequence(env,bids=(600,500,550)):
    marks=[]
    for bid in bids:
        marks.append(checkpoint(env,bid=bid,previous=marks[-1] if marks else None))
    return tuple(marks)


def audit(env,marks,**kwargs):
    return inspect_stage90_history(
        env['boundary'],marks,
        current_snapshot=env['book'].snapshot_local_synthetic_portfolio(),**kwargs)


def test_stage90_three_signed_mtm_marks_expose_only_exploratory_synthetic_drawdown(tmp_path):
    env=setup_account(tmp_path)
    marks=sequence(env)
    result=audit(env,marks)
    assert result.checkpoint_count==3
    assert result.last_checkpoint_sha256==marks[-1].record_sha256
    assert result.eligible_for_exploratory_synthetic_drawdown is True
    assert result.exploratory_synthetic_drawdown_percent>0
    assert result.exploratory_synthetic_drawdown_percent<100
    assert result.profit_factor is None and result.expectancy_cents is None
    assert result.real_market_evidence_verified is False
    assert result.independently_replayed_historical_journal is False
    assert result.live_trading_enabled is False and result.broker_orders_transmitted==0
    assert env['book'].snapshot_local_synthetic_portfolio()==marks[-1].snapshot


def test_stage90_single_mark_remains_ineligible(tmp_path):
    env=setup_account(tmp_path)
    single=checkpoint(env)
    report=audit(env,(single,))
    assert report.checkpoint_count==1
    assert report.exploratory_synthetic_drawdown_percent is None
    assert report.eligible_for_exploratory_synthetic_drawdown is False


def test_stage90_history_can_be_empty_without_invented_metrics(tmp_path):
    env=setup_account(tmp_path)
    empty=audit(env,())
    assert empty.checkpoint_count==0
    assert empty.exploratory_synthetic_drawdown_percent is None


@pytest.mark.parametrize('change',[
    'equity','cash','journal_tip','quote','signature','digest','market_flag',
    'previous','journal_revision','unrealized','scope',
])
def test_stage90_attestation_fails_closed_on_modified_signed_evidence(tmp_path,change):
    env=setup_account(tmp_path)
    marks=sequence(env)
    bad=marks[1]
    if change=='equity':
        bad=replace(bad,valuation=replace(bad.valuation,total_hypothetical_equity_cents=
                    bad.valuation.total_hypothetical_equity_cents+1))
    elif change=='cash':
        bad=replace(bad,snapshot=replace(bad.snapshot,cash_cents=bad.snapshot.cash_cents+1))
    elif change=='journal_tip':
        bad=replace(bad,snapshot=replace(bad.snapshot,journal_tip='a'*64))
    elif change=='quote':
        q=bad.quotes[0]
        bad=replace(bad,quotes=(replace(q,bid_cents=q.bid_cents+5),))
    elif change=='signature':
        bad=replace(bad,signature_hex='0'*64)
    elif change=='digest':
        bad=replace(bad,record_sha256='1'*64)
    elif change=='market_flag':
        bad=replace(bad,independent_market_evidence=True)
    elif change=='previous':
        bad=replace(bad,preceding_sha256='b'*64)
    elif change=='journal_revision':
        bad=replace(bad,snapshot=replace(bad.snapshot,journal_revision=987))
    elif change=='unrealized':
        bad=replace(bad,valuation=replace(bad.valuation,unrealized_net_pnl_cents=987))
    else:
        bad=replace(bad,snapshot=replace(bad.snapshot,ledger_scope_sha256='a'*64))
    with pytest.raises(PermissionError):
        audit(env,(marks[0],bad,marks[2]))


@pytest.mark.parametrize('kind',['remove-middle','duplicate','reverse','fork','gap','zero-epoch'])
def test_stage90_rejects_incomplete_nonmonotone_and_gapped_history(tmp_path,kind):
    env=setup_account(tmp_path)
    marks=sequence(env)
    if kind=='remove-middle':
        broken=(marks[0],marks[2])
    elif kind=='duplicate':
        broken=(marks[0],marks[1],marks[1])
    elif kind=='reverse':
        broken=tuple(reversed(marks))
    elif kind=='fork':
        broken=(marks[0],marks[0],marks[2])
    elif kind=='gap':
        env['clock'][0]+=500
        later=checkpoint(env,previous=marks[-1])
        broken=marks+(later,)
    else:
        broken=(replace(marks[0],valuation=replace(marks[0].valuation,valuation_epoch=0)),)+marks[1:]
    with pytest.raises(PermissionError):
        audit(env,broken)


def test_stage90_wrong_key_and_cross_boundary_are_blocked(tmp_path):
    env=setup_account(tmp_path)
    env['clock'][0]+=1
    with pytest.raises(Stage90HistoryBlocked,match='test issuer'):
        capture_stage90_checkpoint(env['book'],env['boundary'],
                                   issuer_key=b'x'*32,quotes=())
    good=checkpoint(env)
    other=setup_account(tmp_path/'other')
    with pytest.raises(PermissionError):
        inspect_stage90_history(other['boundary'],(good,))


def test_stage90_current_head_must_match_signed_final_checkpoint(tmp_path):
    env=setup_account(tmp_path)
    marks=sequence(env)
    altered=replace(env['book'].snapshot_local_synthetic_portfolio(),journal_tip='f'*64)
    with pytest.raises(Stage90HistoryBlocked,match='current ledger head'):
        inspect_stage90_history(env['boundary'],marks,current_snapshot=altered)


def test_stage90_policy_gates_never_make_short_toy_history_official(tmp_path):
    env=setup_account(tmp_path)
    marks=sequence(env,bids=(600,605,610))
    assert audit(env,marks,min_marks=4).exploratory_synthetic_drawdown_percent is None
    assert audit(env,marks,min_span_seconds=99).exploratory_synthetic_drawdown_percent is None
    with pytest.raises(Stage90HistoryBlocked):
        audit(env,marks,min_marks=True)
    with pytest.raises(Stage90HistoryBlocked):
        audit(env,marks,max_gap_seconds=0)


def test_stage90_flat_account_signed_empty_quote_marks_are_supported(tmp_path):
    env=setup_account(tmp_path,filled=False)
    marks=[]
    for _ in range(3):
        marks.append(checkpoint(env,previous=marks[-1] if marks else None,empty=True))
    result=audit(env,tuple(marks))
    assert result.eligible_for_exploratory_synthetic_drawdown is True
    assert result.exploratory_synthetic_drawdown_percent==0.0
    assert result.profit_factor is None


def test_stage90_is_read_only_and_signed_records_do_not_reauthorize_entries(tmp_path):
    env=setup_account(tmp_path)
    before=env['book'].snapshot_local_synthetic_portfolio()
    marks=sequence(env)
    audit(env,marks)
    after=env['book'].snapshot_local_synthetic_portfolio()
    assert after==before
    assert marks[-1].snapshot.journal_revision==before.journal_revision
    assert marks[-1].snapshot.live_trading_enabled is False
