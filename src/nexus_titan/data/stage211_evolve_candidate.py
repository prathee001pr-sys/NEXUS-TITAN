"""Stage 211: immutable research-only TITAN EVOLVE candidate intake.

A syntactically valid candidate is not a safe strategy or permission to execute code.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re

_SHA=re.compile(r'[0-9a-f]{64}\Z')
_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_ALLOWED_TARGETS=frozenset({'strategy_research','signal_research','offline_backtest','synthetic_evaluation'})

@dataclass(frozen=True,slots=True)
class EvolveCandidate:
    candidate_id: str
    proposer_id: str
    research_target: str
    hypothesis: str
    code_sha256: str
    dataset_sha256: str
    baseline_sha256: str

@dataclass(frozen=True,slots=True)
class CandidateIntakeReceipt:
    eligible_for_offline_research: bool
    candidate_sha256: str
    blockers: tuple[str,...]
    code_execution_authorized: bool=False
    risk_change_authorized: bool=False
    live_trading_authorized: bool=False
    autonomous_execution_authorized: bool=False
    strategy_promotion_authorized: bool=False

def audit_evolve_candidate(candidate: EvolveCandidate, *, execution_requested: bool=False,
                           risk_change_requested: bool=False, live_requested: bool=False,
                           autonomous_requested: bool=False, promotion_requested: bool=False)->CandidateIntakeReceipt:
    checks={
        'typed immutable candidate':type(candidate) is EvolveCandidate,
        'execution prohibited':execution_requested is False,
        'risk modifications prohibited':risk_change_requested is False,
        'live trading prohibited':live_requested is False,
        'autonomous execution prohibited':autonomous_requested is False,
        'promotion prohibited':promotion_requested is False,
    }
    if type(candidate) is EvolveCandidate:
        checks.update({
            'safe candidate ID':type(candidate.candidate_id) is str and bool(_ID.fullmatch(candidate.candidate_id)),
            'safe proposer ID':type(candidate.proposer_id) is str and bool(_ID.fullmatch(candidate.proposer_id)),
            'research-only target':type(candidate.research_target) is str and candidate.research_target in _ALLOWED_TARGETS,
            'bounded nonempty hypothesis':type(candidate.hypothesis) is str and 12<=len(candidate.hypothesis.strip())<=1000 and '\x00' not in candidate.hypothesis,
            'code fingerprint':type(candidate.code_sha256) is str and bool(_SHA.fullmatch(candidate.code_sha256)),
            'data fingerprint':type(candidate.dataset_sha256) is str and bool(_SHA.fullmatch(candidate.dataset_sha256)),
            'baseline fingerprint':type(candidate.baseline_sha256) is str and bool(_SHA.fullmatch(candidate.baseline_sha256)),
        })
    blockers=tuple(k for k,ok in checks.items() if not ok)
    digest=hashlib.sha256(json.dumps({k:getattr(candidate,k) for k in ('candidate_id','proposer_id','research_target','hypothesis','code_sha256','dataset_sha256','baseline_sha256')},sort_keys=True,separators=(',',':')).encode()).hexdigest() if not blockers else ''
    return CandidateIntakeReceipt(not blockers,digest,blockers)
