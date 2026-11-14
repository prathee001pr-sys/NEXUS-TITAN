"""Strict offline Stage 222 candidate-vs-baseline equivalence and safety tests."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from nexus_titan.data.stage217_progress_journal import (
    ProgressEvent, audit_progress_journal, make_progress_event,
)
from nexus_titan.diagnostics.stage222_journal_candidate import (
    audit_progress_journal_candidate, _validated_canonical_event_digest,
)


def _one(state='SUBMITTED_UNVERIFIED', evidence='b'*64):
    return make_progress_event(sequence=1,stage_number=216,state=state,
           evidence_sha256=evidence,previous_event_sha256='0'*64)


def _match(case):
    assert audit_progress_journal_candidate(case)==audit_progress_journal(case)
    return audit_progress_journal(case)


@pytest.mark.parametrize('count',[1,2,5,30,300,1000])
def test_222_good_journal_matches_original(count):
    prev='0'*64; events=[]
    for i in range(count):
        ev=make_progress_event(sequence=i+1,stage_number=216+i%5,
                state=('SUBMITTED_UNVERIFIED','LOCAL_TEST_REPORTED_UNVERIFIED','CI_REPORTED_UNVERIFIED')[i%3],
                evidence_sha256=hashlib.sha256(str(i).encode()).hexdigest(),
                previous_event_sha256=prev)
        events.append(ev);prev=ev.event_sha256
    receipt=_match(tuple(events))
    assert receipt.accepted and not receipt.authoritative_git_verification
    assert not receipt.live_trading_authorized


@pytest.mark.parametrize('bad',[None,[],{},(),tuple([None]),tuple([_one()]*1001), True, 'bad'])
def test_222_invalid_container_consistent(bad):
    assert not _match(bad).accepted


@pytest.mark.parametrize('field,value',[('sequence',True),('sequence',0),('sequence',1001),
    ('stage_number',True),('stage_number',0),('stage_number',221),
    ('state','BAD'),('state',None),('state',True),
    ('evidence_sha256','bad'),('evidence_sha256','Z'*64),('evidence_sha256',False),
    ('previous_event_sha256',False),('previous_event_sha256','Z'*64),
    ('event_sha256','a'*64),('event_sha256',True)])
def test_222_mutated_record_rejected_same_way(field,value):
    invalid=replace(_one(),**{field:value})
    receipt=_match((invalid,))
    assert not receipt.accepted


@pytest.mark.parametrize('state',['SUBMITTED_UNVERIFIED','LOCAL_TEST_REPORTED_UNVERIFIED','CI_REPORTED_UNVERIFIED'])
def test_222_canonical_encoding_exact(state):
    event=_one(state)
    assert _validated_canonical_event_digest(event)==event.event_sha256
    assert _match((event,)).accepted


def test_222_invalid_link_and_duplicate_and_reordering():
    a=_one();b=make_progress_event(sequence=2,stage_number=217,
          state='CI_REPORTED_UNVERIFIED',evidence_sha256='c'*64,previous_event_sha256=a.event_sha256)
    for case in ((b,), (a,a),(b,a), (a,replace(b,previous_event_sha256='a'*64)),
                 (a,replace(b,event_sha256='z'*64)),(a,replace(b,sequence=3))):
        assert not _match(case).accepted


def test_222_randomized_adversarial_edits_repeatable():
    rng=random.Random(222)
    good=_one()
    for _ in range(100):
        choice=rng.randrange(5)
        if choice==0:bad=replace(good,sequence=rng.choice([-1,0,2,1001,True]))
        elif choice==1:bad=replace(good,stage_number=rng.choice([0,221,False,'X']))
        elif choice==2:bad=replace(good,state=rng.choice(['YES','CI_REPORTED_VERIFIED',False]))
        elif choice==3:bad=replace(good,evidence_sha256=rng.choice(['bad','A'*64,None]))
        else:bad=replace(good,event_sha256=rng.choice(['bad',None,'f'*64]))
        assert not _match((bad,)).accepted


def test_222_source_untouched_and_experimental_not_imported_by_production():
    source=Path(__file__).resolve().parents[1]/'src/nexus_titan/data/stage217_progress_journal.py'
    assert 'stage222' not in source.read_text()
    stage217=importlib.import_module('nexus_titan.data.stage217_progress_journal')
    assert stage217.audit_progress_journal is audit_progress_journal


def test_222_cli_bounded_report(tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts/run_stage222_comparison.py'
    path=tmp_path/'report.json'
    r=subprocess.run([sys.executable,str(script),'--samples','3','--iterations','1',
                      '--json-out',str(path)],capture_output=True,text=True,timeout=35)
    assert r.returncode==0,r.stderr
    report=json.loads(path.read_text())
    assert report['schema']=='titan.stage222.offline_python_candidate.v1'
    assert [x['event_count'] for x in report['results']]==[30,300,1000]
    assert all(x['equivalent_on_fixed_fixture'] for x in report['results'])
    assert not report['live_trading_authorized']
    assert not report['production_replacement_authorized']
    assert not report['rust_rewrite_authorized']
    assert not report['real_market_latency_verified']


@pytest.mark.parametrize('flag,val',[('--samples','2'),('--samples','32'),('--iterations','0'),('--iterations','101')])
def test_222_cli_invalid_limits(flag,val,tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts/run_stage222_comparison.py'
    path=tmp_path/'never.json'
    r=subprocess.run([sys.executable,str(script),flag,val,'--json-out',str(path)],
                     capture_output=True,text=True,timeout=10)
    assert r.returncode==2 and not path.exists()
