"""These integration tests activate only on the exact Stage95 full repository."""
import runpy
from pathlib import Path
import pytest
from nexus_titan.operations.stage96_accounting_review import selected_fo_scorecard

ROOT=Path(__file__).resolve().parents[1]
STAGE95=ROOT/'tests'/'test_stage95_fo_closed_trade_pipeline.py'

@pytest.mark.skipif(not STAGE95.is_file(),reason='Exact Stage95 checkout required; not in standalone candidate')
def test_actual_stage95_closed_trade_pipeline_and_accounting(tmp_path):
    h=runpy.run_path(str(STAGE95))
    env,pipeline=h['setup'](tmp_path)
    op,_=h['open_order'](env,pipeline)
    h['fill_order'](env,pipeline,op)
    h['fill_order'](env,pipeline,op,fill_id='fill-2')
    h['close_order'](env,pipeline,op.order_id)
    h['close_order'](env,pipeline,op.order_id,operation_id='close-2')
    r=selected_fo_scorecard(pipeline)
    assert r['market']=='INDIAN_FO' and r['currency']=='INR'
    assert r['journal_revision']>=3
    assert r['realized_net_pnl_cents']==pipeline.dashboard()['performance']['realized_net_pnl_cents']
    assert r['position_count']==0 and r['closed_position_count']==1
    assert not r['live_trading_enabled'] and not r['real_market_shadow_validated']

@pytest.mark.skipif(not STAGE95.is_file(),reason='Exact Stage95 checkout required; not in standalone candidate')
def test_actual_stage95_open_without_market_evidence_has_no_equity(tmp_path):
    h=runpy.run_path(str(STAGE95))
    env,pipeline=h['setup'](tmp_path)
    op,_=h['open_order'](env,pipeline)
    h['fill_order'](env,pipeline,op)
    r=selected_fo_scorecard(pipeline)
    assert r['position_count']==1
    assert r['synthetic_equity_cents'] is None
    assert r['profit_factor'] is None
