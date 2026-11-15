"""Stage224 final offline evidence gate: explicitly *not* production certification."""
from __future__ import annotations
from dataclasses import FrozenInstanceError
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from nexus_titan.diagnostics.stage224_final_audit import (
    Stage224FinalAuditReceipt, evaluate_stage224_final_audit,
    safe_stage224_evidence_template, _valid_evidence, _pinned_sources,
)

ROOT=Path(__file__).resolve().parents[1]
STAGE222=ROOT/'reports/STAGE222_LOCAL_PYTHON_AB_2026-11-14.json'
SCRIPT=ROOT/'scripts/run_stage224_final_audit.py'


def report():
    return json.loads(STAGE222.read_text())


def evidence(**overrides):
    e=safe_stage224_evidence_template()
    e.update(overrides)
    return e


_MISSING=object()

def review(e=_MISSING, r=_MISSING):
    return evaluate_stage224_final_audit(report() if r is _MISSING else r,
                                         evidence() if e is _MISSING else e)


def test_local_source_pins_match_the_stage223_parent_snapshot():
    assert _pinned_sources(ROOT)


def test_safe_template_explicitly_claims_nothing():
    e=evidence()
    assert _valid_evidence(e)==(True,())
    assert e['run_scope']=='NOT_RUN' and not e['full_suite_run_completed']
    assert not e['live_trading_enabled'] and not e['risk_controls_changed']
    assert not e['authoritative_ci_proof_supplied']
    assert not e['recovery_root_cause_proven']


def test_stage224_accepts_only_offline_evidence_record_and_retains_no_go():
    x=review()
    assert x.accepted_for_offline_evidence_record
    assert x.stage223_consistency_verified_locally
    assert x.parent_sources_pinned_locally
    assert len(x.local_evidence_digest_sha256)==64
    assert x.blockers
    assert any('recovery' in s.lower() for s in x.blockers)
    for name in ('full_regression_verified','independent_recovery_root_cause_verified',
                 'authoritative_github_ci_verified','external_market_data_verified',
                 'rust_integration_justified','production_replacement_authorized',
                 'risk_controls_change_authorized','broker_orders_authorized',
                 'autonomous_execution_authorized','live_trading_authorized'):
        assert getattr(x,name) is False
    with pytest.raises(FrozenInstanceError):
        x.live_trading_authorized=True


def test_deterministic_digest_for_same_untrusted_evidence():
    a=review()
    b=review()
    assert a==b
    assert a.local_evidence_digest_sha256 == hashlib.sha256(json.dumps(
        evidence(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def test_targeted_957_tests_cannot_certify_full_regression():
    x=review(evidence(run_scope='TARGETED',local_pytest_passed=957))
    assert x.accepted_for_offline_evidence_record
    assert not x.full_regression_verified
    assert any('full repository' in s.lower() for s in x.blockers)


def test_reported_full_green_is_not_independent_cicertification():
    x=review(evidence(run_scope='BOUNDED_FULL', full_suite_run_completed=True,
                      local_pytest_passed=4600,recovery_runs=3))
    assert x.accepted_for_offline_evidence_record
    assert not x.full_regression_verified and not x.authoritative_github_ci_verified
    assert not x.independent_recovery_root_cause_verified
    assert not x.live_trading_authorized


def test_legacy_failures_remain_visible():
    x=review(evidence(run_scope='BOUNDED_FULL',full_suite_run_completed=True,
                      local_pytest_passed=4564,local_pytest_failed=2,
                      local_pytest_skipped=2,recovery_runs=3,recovery_unexpected=2))
    assert x.accepted_for_offline_evidence_record
    assert any('observed local regression failures' in s.lower() for s in x.blockers)
    assert any('unexpected recovery' in s.lower() for s in x.blockers)


@pytest.mark.parametrize('replacement',[None,False,True,1,'not JSON',[],(),1.2])
def test_malformed_evidence_rejected(replacement):
    x=review(replacement)
    assert not x.accepted_for_offline_evidence_record
    assert x.local_evidence_digest_sha256==''
    assert not x.live_trading_authorized


@pytest.mark.parametrize('field',list(safe_stage224_evidence_template().keys()))
def test_missing_field_rejected(field):
    e=evidence();e.pop(field)
    assert not review(e).accepted_for_offline_evidence_record


@pytest.mark.parametrize('bad', [None,True,1,'TRUE',[],{},float('nan')])
def test_unknown_or_unsafe_flag_rejected(bad):
    for key in ('recovery_root_cause_proven','authoritative_ci_proof_supplied',
                'external_market_data_verified','live_trading_enabled','risk_controls_changed'):
        e=evidence(**{key:bad})
        assert not review(e).accepted_for_offline_evidence_record


@pytest.mark.parametrize('field',('local_pytest_passed','local_pytest_failed','local_pytest_skipped',
                                  'recovery_runs','recovery_unexpected'))
@pytest.mark.parametrize('value',(-1,True,1.1,'0',100001))
def test_invalid_count_rejected(field,value):
    assert not review(evidence(**{field:value})).accepted_for_offline_evidence_record


@pytest.mark.parametrize('field,value',[('run_scope','FULL'),('run_scope',True),
    ('run_scope',None),('full_suite_run_completed',None),('full_suite_run_completed',1),
    ('broker_orders_sent',True),('broker_orders_sent',1),('broker_orders_sent',None),
    ('schema','bogus'),('schema',None)])
def test_invalid_status_or_offline_contract_rejected(field,value):
    assert not review(evidence(**{field:value})).accepted_for_offline_evidence_record


def test_run_scope_contradictions_rejected():
    for e in (
        evidence(local_pytest_passed=1),
        evidence(full_suite_run_completed=True),
        evidence(run_scope='TARGETED',full_suite_run_completed=True),
        evidence(run_scope='BOUNDED_FULL'),
        evidence(recovery_runs=1,recovery_unexpected=2),
        evidence(extra_key='forged'),
    ):
        assert not review(e).accepted_for_offline_evidence_record


def test_tampered_parent_report_rejected():
    r=report();r['results'][0]['candidate_median_ns']+=1
    x=review(evidence(),r)
    assert not x.stage223_consistency_verified_locally
    assert not x.accepted_for_offline_evidence_record
    assert not x.rust_integration_justified


def test_empty_or_invalid_parent_report_rejected():
    for r in (None, [], 'schema', {}, True):
        assert not review(evidence(),r).accepted_for_offline_evidence_record


def test_mismatched_source_root_rejected(tmp_path):
    x=evaluate_stage224_final_audit(report(),evidence(),project_root=tmp_path)
    assert not x.parent_sources_pinned_locally
    assert not x.accepted_for_offline_evidence_record


def _run(*args):
    return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True,
                          cwd=ROOT,timeout=25)


def test_cli_default_records_explicit_no_go():
    c=_run()
    assert c.returncode==0,c.stderr
    data=json.loads(c.stdout)
    assert data['schema']=='titan.stage224.final_offline_review.v1'
    assert data['production_release']=='NO_GO' and data['rust_integration']=='NO_GO'
    assert data['live_trading_authorized'] is False
    assert data['receipt']['full_regression_verified'] is False


def test_cli_valid_targeted_evidence_never_promotes(tmp_path):
    inp=tmp_path/'evidence.json'; out=tmp_path/'result.json'
    inp.write_text(json.dumps(evidence(run_scope='TARGETED',local_pytest_passed=1068)))
    c=_run('--local-evidence',inp,'--json-out',out)
    assert c.returncode==0,c.stderr
    data=json.loads(out.read_text())
    assert data['receipt']['accepted_for_offline_evidence_record']
    assert data['receipt']['blockers']
    assert data['receipt']['live_trading_authorized'] is False
    c=_run('--local-evidence',inp,'--json-out',out)
    assert c.returncode==2 and out.exists() # never overwrite previous audit


def test_cli_bad_evidence_does_not_write_accepted_report(tmp_path):
    inp=tmp_path/'bad.json'; out=tmp_path/'accepted.json'
    inp.write_text(json.dumps(evidence(live_trading_enabled=True)))
    c=_run('--local-evidence',inp,'--json-out',out)
    assert c.returncode==2 and not out.exists()


def test_cli_malformed_json_not_written(tmp_path):
    inp=tmp_path/'bad.json';out=tmp_path/'accepted.json'
    inp.write_text('{broken')
    assert _run('--local-evidence',inp,'--json-out',out).returncode==2
    assert not out.exists()


def test_cli_non_finite_json_not_written(tmp_path):
    inp=tmp_path/'bad.json';out=tmp_path/'accepted.json'
    inp.write_text('{"bad": NaN}')
    assert _run('--local-evidence',inp,'--json-out',out).returncode==2
    assert not out.exists()


def test_cli_symlinked_input_rejected(tmp_path):
    a=tmp_path/'real.json'; b=tmp_path/'link.json';out=tmp_path/'accepted.json'
    a.write_text(json.dumps(evidence()));b.symlink_to(a)
    assert _run('--local-evidence',b,'--json-out',out).returncode==2
    assert not out.exists()


def test_cli_oversized_input_rejected(tmp_path):
    a=tmp_path/'oversized.json';out=tmp_path/'accepted.json'
    a.write_text(' '*100_001)
    assert _run('--local-evidence',a,'--json-out',out).returncode==2
    assert not out.exists()


def test_cli_symlinked_output_rejected(tmp_path):
    target=tmp_path/'target.json'; link=tmp_path/'alias.json'
    target.write_text('no-clobber');link.symlink_to(target)
    assert _run('--json-out',link).returncode==2
    assert target.read_text()=='no-clobber'


def test_cli_bad_stage222_report_rejected(tmp_path):
    inp=tmp_path/'tamper.json';out=tmp_path/'accepted.json'
    r=report();r['results'][1]['fixture_digest']='f'*64
    inp.write_text(json.dumps(r))
    assert _run('--stage222-report',inp,'--json-out',out).returncode==2
    assert not out.exists()


def test_cli_source_code_is_offline_read_only():
    content=SCRIPT.read_text()
    assert 'broker' not in content.lower() or 'never' in content.lower()
    x=review()
    assert not any(getattr(x,k) for k in (
        'broker_orders_authorized','autonomous_execution_authorized',
        'live_trading_authorized','rust_integration_justified'))
