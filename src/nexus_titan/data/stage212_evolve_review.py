"""Stage 212: independent human-review attestation for *offline research only*.

Names/approval are caller-provided attestations, not authenticated identities.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from .stage211_evolve_candidate import CandidateIntakeReceipt,EvolveCandidate,audit_evolve_candidate
_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')

@dataclass(frozen=True,slots=True)
class OfflineReview:
    candidate_id:str
    candidate_sha256:str
    reviewer_id:str
    decision:str  # APPROVE_OFFLINE_RESEARCH or REJECT
    risk_policy_sha256:str

@dataclass(frozen=True,slots=True)
class OfflineReviewReceipt:
    eligible_for_offline_research:bool
    review_sha256:str
    blockers:tuple[str,...]
    reviewer_identity_authenticated:bool=False
    code_execution_authorized:bool=False
    risk_change_authorized:bool=False
    live_trading_authorized:bool=False
    autonomous_execution_authorized:bool=False
    strategy_promotion_authorized:bool=False

def audit_evolve_review(candidate:EvolveCandidate,review:OfflineReview,*,
                        live_requested:bool=False,execution_requested:bool=False,
                        risk_change_requested:bool=False,promotion_requested:bool=False)->OfflineReviewReceipt:
    c=audit_evolve_candidate(candidate)
    checks={'Stage211 candidate revalidated':c.eligible_for_offline_research and not c.blockers,
            'typed review':type(review) is OfflineReview,
            'live prohibited':live_requested is False,
            'execution prohibited':execution_requested is False,
            'risk change prohibited':risk_change_requested is False,
            'promotion prohibited':promotion_requested is False}
    if type(review) is OfflineReview and type(candidate) is EvolveCandidate:
        checks.update({'candidate ID linked':review.candidate_id==candidate.candidate_id,
            'candidate SHA linked':review.candidate_sha256==c.candidate_sha256 and bool(c.candidate_sha256),
            'independent reviewer ID':type(review.reviewer_id) is str and bool(_ID.fullmatch(review.reviewer_id)) and review.reviewer_id!=candidate.proposer_id,
            'offline review only':review.decision=='APPROVE_OFFLINE_RESEARCH',
            'risk policy locked':type(review.risk_policy_sha256) is str and bool(re.fullmatch('[0-9a-f]{64}',review.risk_policy_sha256))})
    blockers=tuple(k for k,ok in checks.items() if not ok)
    digest=hashlib.sha256(json.dumps({'candidate':c.candidate_sha256,'reviewer':review.reviewer_id,'decision':review.decision,'risk':review.risk_policy_sha256},sort_keys=True,separators=(',',':')).encode()).hexdigest() if not blockers else ''
    return OfflineReviewReceipt(not blockers,digest,blockers)
