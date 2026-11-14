"""Stage 216–220: synthetic/read-only progress, adversarial evidence and local backup tests.

No test in this file claims verified GitHub provenance, owner authentication,
production trade permissions, or secure cloud deployment.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import stat

import pytest

from nexus_titan.data.stage215_evolve_no_go_gate import EvolveSafetyNoGoReceipt
from nexus_titan.data.stage216_progress_evidence import (
    StageProgressEvidence, StageEvidenceIntakeReceipt, audit_stage_progress_evidence,
    sha_ok, canonical_digest,
)
from nexus_titan.data.stage217_progress_journal import (
    ProgressEvent, ProgressJournalReceipt, make_progress_event, audit_progress_journal,
)
from nexus_titan.data.stage218_dashboard_projection import (
    DashboardProjection, StageProgressRow, project_offline_progress,
    audit_dashboard_projection, projection_digest,
)
from nexus_titan.data.stage219_progress_backup import (
    OfflineBackupReceipt, save_local_progress_snapshot,
    load_local_progress_snapshot,
)
from nexus_titan.data.stage220_offline_progress_no_go import (
    OfflineProgressNoGoReceipt, evaluate_offline_progress_no_go,
)

H = 'a' * 64
OTHER = 'b' * 64
COMMIT = '45611a7024ec58c89e45fc08dfd7fc825dfc5d6d'
BRANCH = 'feature/stages211-215-evolve-risk-no-go-2026-11-13'


def sample_evidence():
    return StageProgressEvidence(215, 'prathee001pr-sys/NEXUS-TITAN', BRANCH,
                                 COMMIT, 'c' * 64, 778, 'success', 'success', H)


def sample_context(tmp_path):
    baseline = EvolveSafetyNoGoReceipt(True, H, ())
    evidence = sample_evidence()
    intake = audit_stage_progress_evidence(evidence)
    assert intake.accepted_for_offline_progress_tracking
    event = make_progress_event(sequence=1, stage_number=215,
                                state='CI_REPORTED_UNVERIFIED',
                                evidence_sha256=intake.evidence_sha256,
                                previous_event_sha256='0' * 64)
    events = (event,)
    journal = audit_progress_journal(events)
    dashboard = project_offline_progress(events)
    backup_path = tmp_path / 'progress-snapshot.json'
    backup_receipt = save_local_progress_snapshot(dashboard, backup_path)
    assert backup_receipt.accepted
    return dict(baseline=baseline, evidence=evidence, intake=intake,
                events=events, journal=journal, dashboard=dashboard,
                backup_path=backup_path)


def test_216_accepts_a_real_git_sha1_oid_but_never_verifies_origin():
    rec = audit_stage_progress_evidence(sample_evidence())
    assert rec.accepted_for_offline_progress_tracking and rec.stage_number == 215
    assert sha_ok(rec.evidence_sha256) and not rec.github_source_independently_verified
    assert not rec.tests_independently_verified and not rec.production_or_live_authorized


def test_216_accepts_sha256_git_oid_label_but_does_not_authenticate():
    record = replace(sample_evidence(), commit_oid='d' * 64)
    assert audit_stage_progress_evidence(record).accepted_for_offline_progress_tracking


@pytest.mark.parametrize('field,value', [
    ('stage_number', 0), ('stage_number', 221), ('stage_number', True),
    ('stage_number', '215'), ('repository', 'other/repo'), ('repository', None),
    ('branch', 'main'), ('branch', 'feature/../main'), ('branch', 'feature//x'),
    ('branch', 'feature/trailing/'), ('branch', 'feature/a b'),
    ('branch', 'feature/x\x00'), ('branch', 'feature/' + 'a' * 151),
    ('branch', 'feature/a@{0}'), ('commit_oid', 'd' * 39), ('commit_oid', 'g' * 40),
    ('commit_oid', 'D' * 40), ('commit_oid', True),
    ('test_report_sha256', 'X' * 64), ('test_report_sha256', ''),
    ('test_count_reported', True), ('test_count_reported', 0),
    ('test_count_reported', 100001), ('github_ci_reported', 'verified'),
    ('github_ci_reported', True), ('secret_scan_reported', 'approved'),
    ('linked_research_evidence_sha256', 'e' * 63),
])
def test_216_fail_closed_on_invalid_evidence(field, value):
    rec = audit_stage_progress_evidence(replace(sample_evidence(), **{field:value}))
    assert not rec.accepted_for_offline_progress_tracking
    assert rec.blockers and rec.evidence_sha256 == ''
    assert not rec.production_or_live_authorized


@pytest.mark.parametrize('bad', [None, {}, 'claim', True, object(), []])
def test_216_wrong_record_type(bad):
    assert not audit_stage_progress_evidence(bad).accepted_for_offline_progress_tracking


def test_216_attested_ci_failed_still_unverified_record():
    rec = audit_stage_progress_evidence(replace(sample_evidence(), github_ci_reported='failed'))
    assert rec.accepted_for_offline_progress_tracking  # Record intake only, not a green gate.
    assert not rec.github_source_independently_verified


def test_217_valid_chained_journal_and_last_progress_event():
    first = make_progress_event(sequence=1, stage_number=215, state='SUBMITTED_UNVERIFIED',
                                evidence_sha256=H, previous_event_sha256='0' * 64)
    second = make_progress_event(sequence=2, stage_number=215, state='CI_REPORTED_UNVERIFIED',
                                 evidence_sha256=OTHER, previous_event_sha256=first.event_sha256)
    receipt = audit_progress_journal((first, second))
    assert receipt.accepted and receipt.event_count == 2
    assert receipt.head_sha256 == second.event_sha256
    assert not receipt.authoritative_git_verification and not receipt.live_trading_authorized


@pytest.mark.parametrize('field,value', [
    ('sequence', 0), ('sequence', True), ('sequence', 1001),
    ('stage_number', 0), ('stage_number', 221), ('stage_number', True),
    ('state', 'VERIFIED'), ('state', 'READY_LIVE'), ('state', None),
    ('evidence_sha256', 'x' * 64), ('evidence_sha256', True),
    ('previous_event_sha256', ''), ('previous_event_sha256', 'Z' * 64),
])
def test_217_constructor_rejects_unsafe_fields(field,value):
    fields = dict(sequence=1,stage_number=215,state='SUBMITTED_UNVERIFIED',
                  evidence_sha256=H,previous_event_sha256='0'*64)
    fields[field] = value
    with pytest.raises(ValueError):
        make_progress_event(**fields)


@pytest.mark.parametrize('mutate', [
    lambda e: replace(e, event_sha256=OTHER),
    lambda e: replace(e, evidence_sha256=OTHER),
    lambda e: replace(e, previous_event_sha256=OTHER),
    lambda e: replace(e, sequence=2),
    lambda e: replace(e, state='VERIFIED'),
    lambda e: replace(e, stage_number=0),
    lambda e: replace(e, stage_number=True),
    lambda e: replace(e, event_sha256=True),
])
def test_217_rejects_tampered_event(mutate):
    first = make_progress_event(sequence=1, stage_number=215,state='SUBMITTED_UNVERIFIED',
                                evidence_sha256=H,previous_event_sha256='0' * 64)
    assert not audit_progress_journal((mutate(first),)).accepted


def test_217_rejects_broken_second_link():
    first = make_progress_event(sequence=1,stage_number=215,state='SUBMITTED_UNVERIFIED',
                                evidence_sha256=H,previous_event_sha256='0' * 64)
    second = make_progress_event(sequence=2,stage_number=215,state='CI_REPORTED_UNVERIFIED',
                                 evidence_sha256=H,previous_event_sha256='0' * 64)
    assert not audit_progress_journal((first,second)).accepted


@pytest.mark.parametrize('bad', [[], (), None, {}, 5, 'events', (object(),)])
def test_217_bad_journal_input(bad):
    assert not audit_progress_journal(bad).accepted


def test_218_projection_all_stages_unverified(tmp_path):
    ctx = sample_context(tmp_path)
    p = ctx['dashboard']
    assert audit_dashboard_projection(p) and p.stage_limit == 220
    assert len(p.rows) == 220 and p.rows[214].stage_number == 215
    assert p.rows[214].state == 'CI_REPORTED_UNVERIFIED'
    assert all(not row.independently_verified for row in p.rows)
    assert p.verified_count == 0 and not p.owner_only_auth_verified
    assert not p.live_trading_authorized


def test_218_latest_event_wins_but_remains_unverified():
    e1 = make_progress_event(sequence=1,stage_number=215,state='SUBMITTED_UNVERIFIED',
                             evidence_sha256=H,previous_event_sha256='0' * 64)
    e2 = make_progress_event(sequence=2,stage_number=215,state='CI_REPORTED_UNVERIFIED',
                             evidence_sha256=OTHER,previous_event_sha256=e1.event_sha256)
    p = project_offline_progress((e1,e2))
    assert p.rows[214].evidence_sha256 == OTHER
    assert p.rows[214].state == 'CI_REPORTED_UNVERIFIED'
    assert p.verified_count == 0


@pytest.mark.parametrize('field,value', [
    ('verified_count', 1), ('verified_count', True), ('verified_count', False),
    ('owner_only_auth_verified', True), ('live_trading_authorized', True),
    ('stage_limit', True), ('stage_limit', 221), ('stage_limit', 0),
    ('journal_head_sha256', 'f'*63), ('projection_sha256', 'f'*63),
])
def test_218_rejects_forged_projection_fields(tmp_path, field,value):
    p = sample_context(tmp_path)['dashboard']
    assert not audit_dashboard_projection(replace(p,**{field:value}))


@pytest.mark.parametrize('field,value', [
    ('independently_verified', True), ('state', 'VERIFIED'),
    ('evidence_sha256', 'x'*64), ('stage_number', 0),
    ('state', 'LIVE_READY'),
])
def test_218_rejects_forged_progress_rows(tmp_path,field,value):
    p = sample_context(tmp_path)['dashboard']
    rows = list(p.rows)
    rows[214] = replace(rows[214],**{field:value})
    forged = replace(p, rows=tuple(rows))
    assert not audit_dashboard_projection(forged)


@pytest.mark.parametrize('bad',[0, 221, True, '220', None])
def test_218_invalid_stage_limits(tmp_path,bad):
    with pytest.raises(ValueError):
        project_offline_progress(sample_context(tmp_path)['events'],stage_limit=bad)


def test_218_no_events_cannot_be_projected():
    with pytest.raises(ValueError):
        project_offline_progress(())


def test_219_secure_exclusive_roundtrip_and_permissions(tmp_path):
    ctx = sample_context(tmp_path)
    target = ctx['backup_path']
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    recovered, report = load_local_progress_snapshot(target)
    assert recovered == ctx['dashboard'] and report.accepted
    assert not report.independently_authenticated and not report.offsite_recovery_verified
    assert not report.live_trading_authorized
    again = save_local_progress_snapshot(ctx['dashboard'], target)
    assert not again.accepted and again.blocker
    assert recovered == load_local_progress_snapshot(target)[0]


def test_219_does_not_overwrite_existing_file(tmp_path):
    p = tmp_path / 'existing.json'
    p.write_text('do not overwrite',encoding='utf-8')
    source = sample_context(tmp_path)['dashboard']
    assert not save_local_progress_snapshot(source,p).accepted
    assert p.read_text() == 'do not overwrite'


@pytest.mark.parametrize('mutate', [
    lambda o: o.__setitem__('snapshot_sha256',OTHER),
    lambda o: o['payload'].__setitem__('verified_count',1),
    lambda o: o['payload'].__setitem__('verified_count',True),
    lambda o: o['payload'].__setitem__('schema','titan.offline-progress.v999'),
    lambda o: o['payload']['rows'][214].__setitem__('independently_verified',True),
    lambda o: o['payload']['rows'][214].__setitem__('state','VERIFIED'),
    lambda o: o['payload']['rows'][214].__setitem__('stage_number',999),
    lambda o: o['payload']['rows'][214].__setitem__('evidence_sha256','fake'),
    lambda o: o.__setitem__('unknown_field','x'),
    lambda o: o['payload'].__setitem__('new_field','x'),
])
def test_219_restore_rejects_modified_snapshot(tmp_path,mutate):
    ctx = sample_context(tmp_path)
    obj = json.loads(ctx['backup_path'].read_text())
    mutate(obj)
    ctx['backup_path'].write_text(json.dumps(obj))
    restored, receipt = load_local_progress_snapshot(ctx['backup_path'])
    assert restored is None and not receipt.accepted


def test_219_restore_rejects_rehashed_but_forged_verified_marker(tmp_path):
    ctx = sample_context(tmp_path)
    obj = json.loads(ctx['backup_path'].read_text())
    obj['payload']['rows'][214]['independently_verified'] = True
    obj['snapshot_sha256'] = canonical_digest(obj['payload'])
    ctx['backup_path'].write_text(json.dumps(obj))
    recovered, receipt = load_local_progress_snapshot(ctx['backup_path'])
    assert recovered is None and not receipt.accepted


def test_219_restore_rejects_duplicate_json_keys(tmp_path):
    ctx = sample_context(tmp_path)
    raw = ctx['backup_path'].read_text()
    ctx['backup_path'].write_text(raw.replace('"schema":', '"schema":"evil","schema":', 1))
    assert not load_local_progress_snapshot(ctx['backup_path'])[1].accepted


def test_219_restore_rejects_symlink(tmp_path):
    ctx = sample_context(tmp_path)
    symlink = tmp_path/'symlink.json'
    symlink.symlink_to(ctx['backup_path'])
    assert not load_local_progress_snapshot(symlink)[1].accepted


def test_219_restore_rejects_world_readable_snapshot(tmp_path):
    ctx=sample_context(tmp_path)
    ctx['backup_path'].chmod(0o644)
    assert not load_local_progress_snapshot(ctx['backup_path'])[1].accepted


def test_219_rejects_backup_symlink_directory(tmp_path):
    ctx = sample_context(tmp_path)
    link = tmp_path/'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    assert not save_local_progress_snapshot(ctx['dashboard'],link/'backup.json').accepted


def test_219_rejects_hardlinked_snapshot(tmp_path):
    ctx=sample_context(tmp_path)
    alias=tmp_path/'hardlink.json'
    os.link(ctx['backup_path'],alias)
    assert not load_local_progress_snapshot(alias)[1].accepted


@pytest.mark.parametrize('invalid',[None,5,True,'',Path('/path/that/does/not/exist')])
def test_219_restore_invalid_paths(invalid):
    restored,receipt=load_local_progress_snapshot(invalid)
    assert restored is None and not receipt.accepted


def test_219_rejects_invalid_projection(tmp_path):
    ctx=sample_context(tmp_path)
    bad=replace(ctx['dashboard'],verified_count=1)
    assert not save_local_progress_snapshot(bad,tmp_path/'bad.json').accepted


def test_220_end_to_end_synthetic_tracking_only(tmp_path):
    ctx = sample_context(tmp_path)
    result = evaluate_offline_progress_no_go(**ctx)
    assert result.eligible_for_local_read_only_progress_review and not result.blockers
    assert sha_ok(result.evidence_sha256)
    for fld in ('real_market_evidence_independently_verified',
                'github_checks_independently_verified','owner_only_dashboard_access_verified',
                'public_or_private_deployment_authorized','risk_limits_change_authorized',
                'live_trading_authorized','autonomous_execution_authorized',
                'strategy_promotion_authorized'):
        assert getattr(result,fld) is False
    assert result == evaluate_offline_progress_no_go(**ctx)


@pytest.mark.parametrize('field,mutator', [
    ('baseline',lambda v: replace(v, eligible_for_internal_offline_research_review=False)),
    ('baseline',lambda v: replace(v, live_trading_authorized=True)),
    ('baseline',lambda v: replace(v, evidence_sha256='f'*64)),
    ('baseline',lambda v: replace(v, external_market_data_authenticated=True)),
    ('baseline',lambda v: replace(v, blockers=('block',))),
    ('evidence',lambda v: replace(v, linked_research_evidence_sha256='f'*64)),
    ('evidence',lambda v: replace(v, stage_number=214)),
    ('evidence',lambda v: replace(v, github_ci_reported='failed')),
    ('intake',lambda v: replace(v, evidence_sha256='f'*64)),
    ('intake',lambda v: replace(v, github_source_independently_verified=True)),
    ('journal',lambda v: replace(v, head_sha256='f'*64)),
    ('journal',lambda v: replace(v, authoritative_git_verification=True)),
    ('events',lambda v: v[:-1]),
    ('dashboard',lambda v: replace(v, projection_sha256='f'*64)),
    ('dashboard',lambda v: replace(v, owner_only_auth_verified=True)),
    ('dashboard',lambda v: replace(v, verified_count=1)),
    ('backup_path',lambda v: '/nonexistent/snapshot.json'),
])
def test_220_cross_stage_forgery_fails_closed(tmp_path, field, mutator):
    ctx=sample_context(tmp_path)
    ctx[field]=mutator(ctx[field])
    result=evaluate_offline_progress_no_go(**ctx)
    assert not result.eligible_for_local_read_only_progress_review
    assert result.blockers and not result.evidence_sha256
    assert not result.live_trading_authorized


@pytest.mark.parametrize('field',[ 'live_requested','autonomous_requested','deployment_requested',
                                    'risk_change_requested','promotion_requested'])
def test_220_permission_requests_vetoed(tmp_path,field):
    ctx=sample_context(tmp_path)
    result=evaluate_offline_progress_no_go(**ctx,**{field:True})
    assert not result.eligible_for_local_read_only_progress_review
    assert not result.evidence_sha256 and result.blockers


def test_220_rejects_latest_event_mismatch(tmp_path):
    ctx=sample_context(tmp_path)
    old=ctx['events'][0]
    new=make_progress_event(sequence=2,stage_number=215,state='CI_REPORTED_UNVERIFIED',
                            evidence_sha256=OTHER,previous_event_sha256=old.event_sha256)
    ctx['events']=(old,new)
    ctx['journal']=audit_progress_journal(ctx['events'])
    ctx['dashboard']=project_offline_progress(ctx['events'])
    ctx['backup_path']=tmp_path/'updated.json'
    assert save_local_progress_snapshot(ctx['dashboard'],ctx['backup_path']).accepted
    assert not evaluate_offline_progress_no_go(**ctx).eligible_for_local_read_only_progress_review


def test_220_rejects_valid_journal_but_unrelated_recovery_file(tmp_path):
    ctx=sample_context(tmp_path)
    alt=make_progress_event(sequence=1,stage_number=215,state='SUBMITTED_UNVERIFIED',
                            evidence_sha256=OTHER,previous_event_sha256='0'*64)
    other=project_offline_progress((alt,))
    path=tmp_path/'unrelated.json'
    assert save_local_progress_snapshot(other,path).accepted
    ctx['backup_path']=path
    assert not evaluate_offline_progress_no_go(**ctx).eligible_for_local_read_only_progress_review


def test_219_rejects_nested_symlink_ancestor(tmp_path):
    ctx = sample_context(tmp_path)
    actual = tmp_path/'actual'
    actual.mkdir()
    link = tmp_path/'link'
    link.symlink_to(actual, target_is_directory=True)
    assert not save_local_progress_snapshot(ctx['dashboard'], link/'foo.json').accepted
    dest = actual/'private.json'
    assert save_local_progress_snapshot(ctx['dashboard'], dest).accepted
    assert not load_local_progress_snapshot(link/'private.json')[1].accepted
