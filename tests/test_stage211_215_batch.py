"""Stage 211-215: immutable, read-only synthetic EVOLVE safety review tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from nexus_titan.data.stage210_execution_no_go_gate import SyntheticExecutionNoGoReceipt
from nexus_titan.data.stage211_evolve_candidate import EvolveCandidate,audit_evolve_candidate
from nexus_titan.data.stage212_evolve_review import OfflineReview,audit_evolve_review
from nexus_titan.data.stage213_evolve_holdout import ResearchObservation,audit_evolve_holdout
from nexus_titan.data.stage214_independent_risk_veto import VetoPolicy,VetoSnapshot,audit_independent_risk_veto,fingerprint_veto_policy
from nexus_titan.data.stage215_evolve_no_go_gate import evaluate_evolve_safety_no_go

T=datetime(2024,1,1,tzinfo=timezone.utc)
def sample_candidate():
    return EvolveCandidate('EV-1','researcher_1','strategy_research','Can a causal holdout improve risk adjusted synthetic outcomes?', 'a'*64,'b'*64,'e'*64)

def sample_review(c=None):
    c=c or sample_candidate()
    return OfflineReview(c.candidate_id,audit_evolve_candidate(c).candidate_sha256,'reviewer_2','APPROVE_OFFLINE_RESEARCH',fingerprint_veto_policy(sample_policy()))

def sample_points():
    return (ResearchObservation(T,'TRAIN','50'),ResearchObservation(T+timedelta(days=1),'TRAIN','-30'),ResearchObservation(T+timedelta(days=3),'HOLDOUT','40'),ResearchObservation(T+timedelta(days=4),'HOLDOUT','-10'))

def sample_policy(): return VetoPolicy(2000,800,2500,1500)
def sample_snapshot(): return VetoSnapshot('200','100','400',100,False,True)
def all_valid():
    c=sample_candidate();r=sample_review(c);p=sample_points();policy=sample_policy();snap=sample_snapshot()
    cr=audit_evolve_candidate(c);rr=audit_evolve_review(c,r);hr=audit_evolve_holdout(p,candidate=cr,review=rr);vr=audit_independent_risk_veto(policy,snap)
    # Typed predecessor is a synthetic-only receipt, not independent exchange proof.
    execution=SyntheticExecutionNoGoReceipt(True,'e'*64,())
    return dict(candidate=c,candidate_receipt=cr,review=r,review_receipt=rr,observations=p,holdout=hr,policy=policy,snapshot=snap,veto=vr,execution=execution)

def test_stage211_valid_candidate_is_research_only():
    r=audit_evolve_candidate(sample_candidate()); assert r.eligible_for_offline_research and len(r.candidate_sha256)==64
    assert r==audit_evolve_candidate(sample_candidate())
    assert not r.code_execution_authorized and not r.risk_change_authorized and not r.live_trading_authorized and not r.strategy_promotion_authorized

@pytest.mark.parametrize('field,value',[
    ('candidate_id','../secret'),('candidate_id',''),('candidate_id','a'*65),('candidate_id',True),
    ('proposer_id','bad name'),('proposer_id',''),('research_target','risk_controls'),('research_target','live_trading'),
    ('research_target','permissions'),('research_target','strategy_promotion'),('research_target','__import__'),
    ('research_target',None),('hypothesis','short'),('hypothesis','x'*1001),('hypothesis','123456789012\x00'),
    ('code_sha256','A'*64),('code_sha256','bad'),('dataset_sha256',''*64),('baseline_sha256',True),
])
def test_211_invalid_fingerprint_protected_targets(field,value):
    c=replace(sample_candidate(),**{field:value})
    r=audit_evolve_candidate(c); assert not r.eligible_for_offline_research and r.blockers and not r.candidate_sha256

@pytest.mark.parametrize('arg',[{'execution_requested':True},{'risk_change_requested':True},
    {'live_requested':True},{'autonomous_requested':True},{'promotion_requested':True}])
def test_211_prohibited_authorizations_fail(arg):
    assert not audit_evolve_candidate(sample_candidate(),**arg).eligible_for_offline_research

def test_211_wrong_type_fails():
    assert not audit_evolve_candidate({'candidate_id':'x'}).eligible_for_offline_research

def test_212_independent_reviewer_is_only_attestation():
    c=sample_candidate();r=audit_evolve_review(c,sample_review(c));assert r.eligible_for_offline_research
    assert not r.reviewer_identity_authenticated and not r.code_execution_authorized and not r.risk_change_authorized

@pytest.mark.parametrize('field,value',[('candidate_id','other'),('candidate_sha256','0'*64),
   ('reviewer_id','researcher_1'),('reviewer_id','bad name'),('reviewer_id',''),
   ('decision','APPROVE_LIVE'),('decision','REJECT'),('risk_policy_sha256','a'),('risk_policy_sha256','F'*64)])
def test_212_wrong_approval_or_policy_fails(field,value):
    c=sample_candidate();assert not audit_evolve_review(c,replace(sample_review(c),**{field:value})).eligible_for_offline_research

@pytest.mark.parametrize('arg',[{'live_requested':True},{'execution_requested':True},
   {'risk_change_requested':True},{'promotion_requested':True}])
def test_212_prohibited_approval_requests(arg):
    assert not audit_evolve_review(sample_candidate(),sample_review(),**arg).eligible_for_offline_research

def test_212_research_target_tamper():
    bad=replace(sample_candidate(),research_target='permissions');r=audit_evolve_review(bad,sample_review());assert r.blockers and not r.eligible_for_offline_research

def test_213_valid_causal_holdout():
    a=all_valid();r=a['holdout'];assert r.eligible_for_offline_research and r.holdout_net_pnl==Decimal('30')
    assert r.train_count==2 and r.holdout_count==2 and len(r.evidence_sha256)==64 and not r.real_market_verified

@pytest.mark.parametrize('mutate',[
 lambda p: (p[1],p[0],p[2],p[3]),
 lambda p: (p[0],p[1],p[3],p[2]),
 lambda p: (p[0],p[2],p[1],p[3]),
 lambda p: (p[0],p[1],replace(p[2],observed_at=T+timedelta(days=1,minutes=1)),p[3]),
 lambda p: (p[0],p[1],replace(p[2],observed_at=T+timedelta(days=1)),p[3]),
 lambda p: (p[0],p[1],replace(p[2],observed_at=T+timedelta(days=3)),p[2]),
 lambda p: (p[0],p[1],replace(p[2],observed_at=T+timedelta(days=3)),replace(p[3],observed_at=T+timedelta(days=2))),
 lambda p: (p[0],p[1],replace(p[2],subset='LIVE'),p[3]),
 lambda p: (p[0],p[1],replace(p[2],observed_at=T.replace(tzinfo=None)),p[3]),
 lambda p: (p[0],p[1],replace(p[2],net_pnl='NaN'),p[3]),
 lambda p: (p[0],p[1],replace(p[2],net_pnl='Infinity'),p[3]),
 lambda p: (p[0],p[1],replace(p[2],net_pnl='100000001'),p[3]),
 lambda p: (p[0],p[1],replace(p[2],net_pnl=True),p[3]),
 lambda p: [*p],
 lambda p: (p[0],p[1],p[2]),
])
def test_213_rejects_leakage_malformed_pnl_or_order(mutate):
    a=all_valid();r=audit_evolve_holdout(mutate(a['observations']),candidate=a['candidate_receipt'],review=a['review_receipt']);assert not r.eligible_for_offline_research

@pytest.mark.parametrize('arg',[{'embargo_minutes':0},{'embargo_minutes':True},{'embargo_minutes':50000},
 {'max_holdout_loss':'-1'},{'max_holdout_loss':'NaN'},{'max_holdout_loss':'oops'},{'max_holdout_loss':True},
 {'max_holdout_loss':'0'}])
def test_213_invalid_policy_or_loss_cap(arg):
    a=all_valid(); assert not audit_evolve_holdout(a['observations'],candidate=a['candidate_receipt'],review=a['review_receipt'],**arg).eligible_for_offline_research if arg.get('max_holdout_loss')!='0' else audit_evolve_holdout(a['observations'],candidate=a['candidate_receipt'],review=a['review_receipt'],**arg).eligible_for_offline_research

def test_213_negative_holdout_loss_blocks():
    a=all_valid();points=list(a['observations']);points[2]=replace(points[2],net_pnl='-10000');assert not audit_evolve_holdout(tuple(points),candidate=a['candidate_receipt'],review=a['review_receipt'],max_holdout_loss='100').eligible_for_offline_research

@pytest.mark.parametrize('field,value',[('max_drawdown_bps',0),('max_drawdown_bps',True),('max_daily_loss_bps',10001),
 ('max_open_exposure_bps',-1),('max_market_age_ms',0),('max_market_age_ms',60001),('require_emergency_stop_clear',False)])
def test_214_policy_fail_closed(field,value):
    assert not audit_independent_risk_veto(replace(sample_policy(),**{field:value}),sample_snapshot()).eligible_for_offline_risk_review

@pytest.mark.parametrize('field,value',[('drawdown_bps','NaN'),('drawdown_bps','Infinity'),('drawdown_bps','5000'),
 ('daily_loss_bps','-1'),('daily_loss_bps','1000'),('open_exposure_bps','3000'),
 ('market_age_ms',True),('market_age_ms',2000),('emergency_stop',True),
 ('risk_engine_allows_offline_review',False),('risk_engine_allows_offline_review',1)])
def test_214_veto_on_invalid_stale_stop_and_limits(field,value):
    r=audit_independent_risk_veto(sample_policy(),replace(sample_snapshot(),**{field:value}));assert not r.eligible_for_offline_risk_review and r.blockers

@pytest.mark.parametrize('arg',[{'live_requested':True},{'autonomous_requested':True},{'promotion_requested':True}])
def test_214_never_grants_trading(arg):
    assert not audit_independent_risk_veto(sample_policy(),sample_snapshot(),**arg).eligible_for_offline_risk_review

def test_214_good_metrics_research_only():
    r=audit_independent_risk_veto(sample_policy(),sample_snapshot());assert r.eligible_for_offline_risk_review and not r.independent_runtime_risk_engine_verified and not r.live_trading_authorized

def test_215_linked_end_to_end_offline_only():
    a=all_valid();r=evaluate_evolve_safety_no_go(**a)
    assert r.eligible_for_internal_offline_research_review and len(r.evidence_sha256)==64
    assert not r.external_market_data_authenticated and not r.human_identity_independently_authenticated
    assert not r.executable_changes_authorized and not r.risk_limits_change_authorized
    assert not r.live_trading_authorized and not r.autonomous_execution_authorized and not r.strategy_promotion_authorized
    assert r==evaluate_evolve_safety_no_go(**a)

@pytest.mark.parametrize('field,alter',[('candidate_receipt',lambda x:replace(x,candidate_sha256='f'*64)),
 ('candidate_receipt',lambda x:replace(x,live_trading_authorized=True)),
 ('review_receipt',lambda x:replace(x,review_sha256='f'*64)),
 ('review_receipt',lambda x:replace(x,reviewer_identity_authenticated=True)),
 ('holdout',lambda x:replace(x,evidence_sha256='f'*64)),
 ('holdout',lambda x:replace(x,real_market_verified=True)),
 ('veto',lambda x:replace(x,veto_sha256='f'*64)),
 ('veto',lambda x:replace(x,live_trading_authorized=True)),
 ('execution',lambda x:replace(x,live_trading_authorized=True)),
 ('execution',lambda x:replace(x,exchange_fee_schedule_verified=True)),
 ('execution',lambda x:replace(x,evidence_sha256='bad')),
 ('execution',lambda x:replace(x,eligible_for_internal_synthetic_execution_review=False)),
 ('candidate',lambda x:replace(x,code_sha256='f'*64)),
 ('review',lambda x:replace(x,risk_policy_sha256='f'*64)),
 ('snapshot',lambda x:replace(x,emergency_stop=True)),
 ('observations',lambda x:x[:-1]),
])
def test_215_forgery_or_mismatch_blocked(field,alter):
    a=all_valid();a[field]=alter(a[field]);r=evaluate_evolve_safety_no_go(**a);assert not r.eligible_for_internal_offline_research_review and r.blockers and not r.evidence_sha256

@pytest.mark.parametrize('arg',[{'live_requested':True},{'autonomous_requested':True},
 {'execution_requested':True},{'risk_change_requested':True},{'promotion_requested':True}])
def test_215_unauthorized_actions_vetoed(arg):
    r=evaluate_evolve_safety_no_go(**all_valid(),**arg);assert not r.eligible_for_internal_offline_research_review


def test_213_non_sequence_input_fails_without_crash():
    a=all_valid()
    for points in (None,5,object()):
        r=audit_evolve_holdout(points,candidate=a['candidate_receipt'],review=a['review_receipt'])
        assert not r.eligible_for_offline_research and r.blockers

def test_215_unapproved_risk_policy_change_blocked():
    a=all_valid();a['policy']=replace(a['policy'],max_drawdown_bps=1500)
    a['veto']=audit_independent_risk_veto(a['policy'],a['snapshot'])
    assert a['veto'].eligible_for_offline_risk_review
    assert not evaluate_evolve_safety_no_go(**a).eligible_for_internal_offline_research_review

def test_215_mismatched_execution_baseline_blocked():
    a=all_valid();a['execution']=replace(a['execution'],evidence_sha256='f'*64)
    assert not evaluate_evolve_safety_no_go(**a).eligible_for_internal_offline_research_review
