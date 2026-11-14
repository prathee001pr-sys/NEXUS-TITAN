"""Stage 215: re-audited offline TITAN EVOLVE and independent Risk & Veto NO-GO gate.

Accepted is permission for human reading of synthetic research evidence ONLY.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from .stage210_execution_no_go_gate import SyntheticExecutionNoGoReceipt
from .stage211_evolve_candidate import EvolveCandidate,CandidateIntakeReceipt,audit_evolve_candidate
from .stage212_evolve_review import OfflineReview,OfflineReviewReceipt,audit_evolve_review
from .stage213_evolve_holdout import ResearchObservation,EvolveHoldoutReceipt,audit_evolve_holdout
from .stage214_independent_risk_veto import VetoPolicy,VetoSnapshot,IndependentVetoReceipt,audit_independent_risk_veto,fingerprint_veto_policy
_SHA=re.compile(r'[0-9a-f]{64}\Z')

@dataclass(frozen=True,slots=True)
class EvolveSafetyNoGoReceipt:
    eligible_for_internal_offline_research_review:bool
    evidence_sha256:str
    blockers:tuple[str,...]
    human_identity_independently_authenticated:bool=False
    external_market_data_authenticated:bool=False
    executable_changes_authorized:bool=False
    risk_limits_change_authorized:bool=False
    live_trading_authorized:bool=False
    autonomous_execution_authorized:bool=False
    strategy_promotion_authorized:bool=False

def evaluate_evolve_safety_no_go(*,candidate:EvolveCandidate,candidate_receipt:CandidateIntakeReceipt,
                                 review:OfflineReview,review_receipt:OfflineReviewReceipt,
                                 observations:tuple[ResearchObservation,...],holdout:EvolveHoldoutReceipt,
                                 policy:VetoPolicy,snapshot:VetoSnapshot,veto:IndependentVetoReceipt,
                                 execution:SyntheticExecutionNoGoReceipt,
                                 embargo_minutes:int=1440,max_holdout_loss:str='10000',
                                 live_requested:bool=False,autonomous_requested:bool=False,
                                 execution_requested:bool=False,risk_change_requested:bool=False,
                                 promotion_requested:bool=False)->EvolveSafetyNoGoReceipt:
    c=audit_evolve_candidate(candidate)
    r=audit_evolve_review(candidate,review)
    h=audit_evolve_holdout(observations,candidate=c,review=r,embargo_minutes=embargo_minutes,max_holdout_loss=max_holdout_loss)
    v=audit_independent_risk_veto(policy,snapshot)
    checks={
        'Stage210 offline execution NO-GO':type(execution) is SyntheticExecutionNoGoReceipt
          and execution.eligible_for_internal_synthetic_execution_review is True and not execution.blockers
          and type(execution.evidence_sha256) is str and bool(_SHA.fullmatch(execution.evidence_sha256))
          and execution.real_market_liquidity_verified is False
          and execution.exchange_fee_schedule_verified is False and execution.historical_execution_verified is False
          and execution.live_trading_authorized is False and execution.autonomous_execution_authorized is False
          and execution.strategy_promotion_authorized is False,
        'Stage211 candidate revalidated':type(candidate_receipt) is CandidateIntakeReceipt and c==candidate_receipt and c.eligible_for_offline_research is True,
        'Stage212 independent review revalidated':type(review_receipt) is OfflineReviewReceipt and r==review_receipt and r.eligible_for_offline_research is True,
        'Stage213 causal holdout revalidated':type(holdout) is EvolveHoldoutReceipt and h==holdout and h.eligible_for_offline_research is True,
        'Stage214 risk veto revalidated':type(veto) is IndependentVetoReceipt and v==veto and v.eligible_for_offline_risk_review is True,
        'approved risk policy fingerprint matches risk veto':type(review) is OfflineReview and review.risk_policy_sha256==fingerprint_veto_policy(policy) and bool(fingerprint_veto_policy(policy)),
        'research baseline links Stage210 receipt':type(candidate) is EvolveCandidate and type(execution) is SyntheticExecutionNoGoReceipt and candidate.baseline_sha256==execution.evidence_sha256,
        'live prohibited':live_requested is False,
        'autonomous execution prohibited':autonomous_requested is False,
        'code execution prohibited':execution_requested is False,
        'risk change prohibited':risk_change_requested is False,
        'strategy promotion prohibited':promotion_requested is False,
    }
    blockers=tuple(k for k,ok in checks.items() if not ok)
    digest=hashlib.sha256(json.dumps({'stage210':execution.evidence_sha256,'stage211':c.candidate_sha256,'stage212':r.review_sha256,'stage213':h.evidence_sha256,'stage214':v.veto_sha256,'scope':'human_read_only_synthetic_evolve_NO_GO'},sort_keys=True,separators=(',',':')).encode()).hexdigest() if not blockers else ''
    return EvolveSafetyNoGoReceipt(not blockers,digest,blockers)
