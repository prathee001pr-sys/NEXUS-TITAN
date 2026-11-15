"""Stage 223: independent, fail-closed review of Stage 222's synthetic report."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from nexus_titan.diagnostics import stage223_rust_readiness as gate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reports/STAGE222_LOCAL_PYTHON_AB_2026-11-14.json'


def report():
    return json.loads(SOURCE.read_text())


def _bad(modifier):
    value=report()
    modifier(value)
    result=gate.review_rust_readiness(value)
    assert not result.accepted_for_offline_experiment_review
    assert not result.report_sha256
    assert not result.observed_speedup_by_event_count
    assert result.blockers
    assert result.rust_integration_justified is False
    assert result.production_replacement_authorized is False
    assert result.live_trading_authorized is False
    assert result.independent_market_data_verified is False
    assert result.independent_recovery_verified is False


def test_223_original_report_accepted_only_for_offline_review():
    receipt=gate.review_rust_readiness(report())
    assert receipt.accepted_for_offline_experiment_review
    assert len(receipt.report_sha256)==64
    assert tuple(x for x,_ in receipt.observed_speedup_by_event_count)==(30,300,1000)
    assert tuple(s for _,s in receipt.observed_speedup_by_event_count)==(2.369,1.901,2.447)
    assert not receipt.rust_integration_justified
    assert not receipt.production_replacement_authorized
    assert not receipt.live_trading_authorized
    assert not receipt.independent_market_data_verified
    assert not receipt.independent_recovery_verified
    assert any('recovery' in blocker.lower() for blocker in receipt.blockers)
    assert receipt==gate.review_rust_readiness(report())
    with pytest.raises(FrozenInstanceError):
        receipt.live_trading_authorized=True


@pytest.mark.parametrize('input_', [None, True, 0, [], (), 'json', object()])
def test_223_bad_top_level_fails_closed(input_):
    r=gate.review_rust_readiness(input_)
    assert not r.accepted_for_offline_experiment_review
    assert not r.rust_integration_justified


@pytest.mark.parametrize('field', [
  'stage217_production_modified', 'production_replacement_authorized',
  'rust_rewrite_authorized', 'live_trading_authorized', 'real_market_latency_verified',
])
@pytest.mark.parametrize('replacement', [True, 'false', 0, None])
def test_223_unsafe_boolean_claims(field,replacement):
    _bad(lambda r:r.__setitem__(field,replacement))


@pytest.mark.parametrize('field, replacement',[
 ('schema','unknown'),('implementation','PyPy'),('python_version',''),
 ('python_version','x'*31),('system',None),('note',''),('samples',True),
 ('samples',2),('samples',32),('samples',9.0),('iterations_per_sample',0),
 ('iterations_per_sample',101),('iterations_per_sample',True),
])
def test_223_metadata_tampering_rejected(field,replacement):
    _bad(lambda r:r.__setitem__(field,replacement))


@pytest.mark.parametrize('field,replacement',[
 ('case','some other journal'),('event_count',True),('event_count',31),
 ('fixture_digest','f'*64),('output_digest','a'*64),
 ('equivalent_on_fixed_fixture',False),('equivalent_on_fixed_fixture',1),
 ('baseline_median_ns',1),('candidate_median_ns',100000),
 ('observed_speedup_ratio',0),('observed_speedup_ratio',999.0),
 ('observed_speedup_ratio',float('nan')),('observed_speedup_ratio',True),
 ('baseline_samples_ns',[]),('candidate_samples_ns',[True]*9),
 ('baseline_samples_ns',[10**20]*9),('candidate_samples_ns',['100']*9),
])
def test_223_workload_tampering_rejected(field,replacement):
    _bad(lambda r:r['results'][1].__setitem__(field,replacement))


def test_223_missing_or_extra_row_rejected():
    _bad(lambda r:r['results'].pop())
    _bad(lambda r:r['results'].append(deepcopy(r['results'][-1])))
    _bad(lambda r:r['results'].reverse())
    _bad(lambda r:r['results'].__setitem__(0,None))


def test_223_extra_or_missing_fields_rejected():
    _bad(lambda r:r.__setitem__('owner_approved',True))
    _bad(lambda r:r.pop('live_trading_authorized'))
    _bad(lambda r:r['results'][0].__setitem__('production_enabled',True))
    _bad(lambda r:r['results'][0].pop('output_digest'))


def test_223_parent_source_byte_fingerprints_enforced(monkeypatch):
    monkeypatch.setattr(gate, '_git_blob_hash', lambda path:'0'*40)
    _bad(lambda r:None)


def test_223_fixed_case_parity_must_hold(monkeypatch):
    from nexus_titan.data.stage217_progress_journal import ProgressJournalReceipt
    monkeypatch.setattr(gate, 'audit_progress_journal_candidate',
                        lambda events:ProgressJournalReceipt(False,0,'',('tampered',)))
    _bad(lambda r:None)


def test_223_runner_generates_no_go_report(tmp_path):
    outfile=tmp_path/'review.json'
    runner=ROOT/'scripts/run_stage223_readiness_review.py'
    result=subprocess.run([sys.executable,str(runner),'--stage222-report',str(SOURCE),
                           '--json-out',str(outfile)],capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr
    parsed=json.loads(outfile.read_text())
    assert parsed['schema']=='titan.stage223.offline_rust_readiness.v1'
    receipt=parsed['receipt']
    assert receipt['accepted_for_offline_experiment_review']
    assert receipt['rust_integration_justified'] is False
    assert receipt['live_trading_authorized'] is False
    assert receipt['production_replacement_authorized'] is False


@pytest.mark.parametrize('bad_json',[ '{', 'null', '{"x":3}', '{"x":NaN}', '[]', 'true'])
def test_223_runner_rejects_untrusted_json(tmp_path,bad_json):
    bad=tmp_path/'input.json';bad.write_text(bad_json)
    out=tmp_path/'out.json'
    runner=ROOT/'scripts/run_stage223_readiness_review.py'
    r=subprocess.run([sys.executable,str(runner),'--stage222-report',str(bad),
                      '--json-out',str(out)],capture_output=True,text=True,timeout=25)
    assert r.returncode==2
    assert not out.exists()


def test_223_production_not_replaced_and_code_is_standalone():
    source=(ROOT/'src/nexus_titan/data/stage217_progress_journal.py').read_text()
    assert 'stage222' not in source and 'stage223' not in source
    candidate=(ROOT/'src/nexus_titan/diagnostics/stage222_journal_candidate.py').read_text()
    assert 'stage223' not in candidate
    from nexus_titan.data.stage217_progress_journal import audit_progress_journal
    assert audit_progress_journal is not gate.audit_progress_journal_candidate
