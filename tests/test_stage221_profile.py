"""Stage 221 synthetic-only Python profiling and watchdog diagnostics."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import json
import subprocess
import sys

import pytest

from nexus_titan.diagnostics.stage221_profile import (
    ProfileCase, ProfileMeasurement, fixed_synthetic_cases,
    measure_case, measurement_to_dict,
)

H = 'a'*64


def fixed_case(op=lambda: H):
    return ProfileCase('unit-safe', 4, H, op, H)


def test_221_only_four_offline_target_names():
    cases=fixed_synthetic_cases()
    assert len(cases)==4
    assert {c.name for c in cases}=={
        'depth_10_levels_each_side', 'synthetic_partial_fill_10_levels',
        'synthetic_closed_trades_1000', 'offline_progress_journal_300'}
    assert all(c.size > 0 for c in cases)
    assert all(len(c.fixture_sha256)==len(c.source_sha256)==64 for c in cases)
    assert all(c.callable_fn()==c.callable_fn() for c in cases)


@pytest.mark.parametrize('index', range(4))
def test_221_each_target_measurement_output_pins_correct_receipt(index):
    c = fixed_synthetic_cases()[index]
    m = measure_case(c, warmups=1, iterations=2, samples=3)
    assert m.name==c.name and m.fixture_sha256==c.fixture_sha256
    assert m.source_sha256==c.source_sha256 and m.output_sha256==c.callable_fn()
    assert m.iterations_per_sample==2 and m.samples==3 and m.warmups==1
    assert 0 < m.min_ns_per_call <= m.median_ns_per_call <= m.p95_ns_per_call <= m.max_ns_per_call
    assert len(m.sample_ns_per_call)==3
    assert not m.live_trading_authorized
    assert not m.rust_rewrite_authorized
    assert not m.real_market_latency_verified
    assert measurement_to_dict(m)['median_ns_per_call']==m.median_ns_per_call


def test_221_fixed_input_digests_reproducible():
    a=fixed_synthetic_cases();b=fixed_synthetic_cases()
    assert [(x.name,x.size,x.fixture_sha256,x.source_sha256,x.callable_fn()) for x in a] == [
        (x.name,x.size,x.fixture_sha256,x.source_sha256,x.callable_fn()) for x in b]


@pytest.mark.parametrize('key,value',[
    ('warmups',0),('warmups',51),('warmups',True),('warmups',1.0),
    ('iterations',0),('iterations',1001),('iterations',False),('iterations',2.0),
    ('samples',0),('samples',2),('samples',52),('samples',True),('samples',3.0),
])
def test_221_bounded_invalid_work_rejected(key,value):
    with pytest.raises(ValueError): measure_case(fixed_case(),**{key:value})


def test_221_mocked_clock_nearest_rank_p95():
    values=iter([0,10,10,50,50,80,80,100,100,115])
    m=measure_case(fixed_case(),warmups=1,iterations=1,samples=5,clock=lambda:next(values))
    assert m.sample_ns_per_call == (10,40,30,20,15)
    assert m.min_ns_per_call==10
    assert m.median_ns_per_call==20
    assert m.p95_ns_per_call==40
    assert m.max_ns_per_call==40


def test_221_non_determinism_fails_closed():
    calls=iter([H,'b'*64])
    with pytest.raises(RuntimeError, match='warmup'):
        measure_case(fixed_case(lambda:next(calls)),warmups=1,iterations=1,samples=3)


def test_221_non_deterministic_timed_iteration_rejected():
    calls=iter([H,H,'b'*64])
    with pytest.raises(RuntimeError,match='non-deterministic'):
        measure_case(fixed_case(lambda:next(calls)),warmups=1,iterations=1,samples=3)


@pytest.mark.parametrize('digest',[None,'bad','g'*64,True,1])
def test_221_invalid_output_rejected(digest):
    with pytest.raises(ValueError,match='output'):
        measure_case(fixed_case(lambda:digest),warmups=1,iterations=1,samples=3)


@pytest.mark.parametrize('bad',[None,'x',42,ProfileCase('bad',0,H,lambda:H,H),
    ProfileCase('bad',1,'BAD',lambda:H,H),ProfileCase('bad',1,H,None,H)])
def test_221_bad_cases_rejected(bad):
    with pytest.raises(ValueError): measure_case(bad,warmups=1,iterations=1,samples=3)


def test_221_invalid_or_reversing_monotonic_clock_rejected():
    times=iter([20,20])
    with pytest.raises(RuntimeError,match='timing'):
        measure_case(fixed_case(),warmups=1,iterations=1,samples=3,clock=lambda:next(times))
    times=iter([20,19])
    with pytest.raises(RuntimeError,match='timing'):
        measure_case(fixed_case(),warmups=1,iterations=1,samples=3,clock=lambda:next(times))


def test_221_model_frozen():
    m=measure_case(fixed_case(),warmups=1,iterations=1,samples=3)
    with pytest.raises(FrozenInstanceError):m.rust_rewrite_authorized=True
    assert not m.live_trading_authorized and not m.rust_rewrite_authorized


def test_221_read_only_cli_writes_profile(tmp_path):
    target=tmp_path/'profile.json'
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_stage221_performance_profile.py'
    result=subprocess.run([sys.executable,str(script),'--warmups','1','--iterations','1',
                          '--samples','3','--json-out',str(target)],capture_output=True,text=True,
                          timeout=25)
    assert result.returncode==0, result.stderr
    data=json.loads(target.read_text())
    assert data['schema']=='titan.stage221.synthetic_python_bench.v1'
    assert not data['live_trading_authorized'] and not data['rust_rewrite_authorized']
    assert not data['real_market_latency_verified']
    assert len(data['profile'])==4


def test_221_cli_invalid_limits_rejected(tmp_path):
    target=tmp_path/'never.json'
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_stage221_performance_profile.py'
    r=subprocess.run([sys.executable,str(script),'--samples','2','--json-out',str(target)],
                     capture_output=True,text=True,timeout=25)
    assert r.returncode==2 and not target.exists()


def test_221_fault_diagnostic_requires_explicit_opt_in():
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_stage221_recovery_variability.py'
    r=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,timeout=15)
    assert r.returncode==2 and 'explicit opt-in' in r.stdout


def test_221_cpu_hotspots_fixed_workloads_and_bounded():
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_stage221_cprofile_hotspots.py'
    r=subprocess.run([sys.executable,str(script),'--iterations','1','--top','3'],
                     capture_output=True,text=True,timeout=25)
    assert r.returncode==0,r.stderr
    report=json.loads(r.stdout)
    assert report['schema']=='titan.stage221.synthetic_hotspots.v1'
    assert not report['rust_rewrite_authorized'] and not report['live_trading_authorized']
    assert len(report['targets'])==4
    assert all(len(x['top_self_cpu_functions'])==3 for x in report['targets'])
    assert all('/' not in f['module_file'] for x in report['targets']
               for f in x['top_self_cpu_functions'])


def test_221_cpu_hotspots_limits_rejected():
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_stage221_cprofile_hotspots.py'
    r=subprocess.run([sys.executable,str(script),'--iterations','51'],
                     capture_output=True,text=True,timeout=25)
    assert r.returncode==2
