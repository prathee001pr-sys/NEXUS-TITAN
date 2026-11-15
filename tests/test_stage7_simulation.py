import pytest
from nexus_titan.simulation.digital_twin import StressScenario, apply_stress
from nexus_titan.simulation.execution_simulator import ExecutionRequest, simulate_execution

BARS=[{"open":100,"high":102,"low":99,"close":101,"volume":1000},{"open":101,"high":103,"low":100,"close":102,"volume":900}]

def test_stress_preserves_source_and_ohlc_invariants():
    result=apply_stress(BARS,StressScenario("gap",gap_pct=-2,intrabar_shock_pct=1,volume_multiplier=.5,spread_multiplier=2))
    assert BARS[0]["open"]==100
    for b in result:
        assert b["high"] >= max(b["open"],b["close"])
        assert b["low"] <= min(b["open"],b["close"])
        assert b["volume"] >= 0

def test_stress_rejects_invalid_bar():
    with pytest.raises(ValueError): apply_stress([{"open":1}],StressScenario("x"))

def test_execution_partial_fill_and_cost():
    r=simulate_execution(ExecutionRequest("BUY",10,100,4,spread_bps=10,slippage_bps=5))
    assert r.status=="PARTIAL" and r.filled_quantity==4 and r.remaining_quantity==6
    assert r.average_fill_price>100 and r.estimated_cost>0

def test_execution_latency_rejection():
    r=simulate_execution(ExecutionRequest("BUY",1,100,1,latency_ms=200,max_latency_ms=100))
    assert r.status=="REJECTED" and r.filled_quantity==0

def test_execution_limit_not_marketable():
    r=simulate_execution(ExecutionRequest("BUY",1,100,1,limit_price=99))
    assert r.status=="UNFILLED"

def test_execution_invalid_request():
    with pytest.raises(ValueError): simulate_execution(ExecutionRequest("BUY",0,100,1))
