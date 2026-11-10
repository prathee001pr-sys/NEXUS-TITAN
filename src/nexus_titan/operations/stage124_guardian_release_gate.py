"""Stage124: release evidence gate for *research-only* Guardian enhancements.

A green local suite is not CI or real-market validation. This module cannot
change risk/permissions or authorize live orders; it only classifies evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_CI = ('3.11', '3.12', '3.13')


@dataclass(frozen=True, slots=True)
class GuardianReleaseEvidence:
    phase03_git_source_verified: bool
    focused_tests_passed: bool
    full_regression_passed: bool
    fault_lab_passed: bool
    python_ci_green: tuple[str, ...] = ()
    secret_scan_green: bool = False
    independent_reviewer_approved: bool = False
    requested_live_trade: bool = False
    risk_veto_runtime_certified: bool = False
    authentic_exchange_data_certified: bool = False


@dataclass(frozen=True, slots=True)
class GuardianReleaseDecision:
    research_candidate_ready: bool
    draft_pr_review_ready: bool
    trade_authorized: bool
    automatic_strategy_promotion: bool
    verdict: str
    reasons: tuple[str, ...]


def review_guardian_release(evidence: GuardianReleaseEvidence) -> GuardianReleaseDecision:
    if not isinstance(evidence, GuardianReleaseEvidence):
        raise TypeError('typed evidence required')
    for name in ('phase03_git_source_verified','focused_tests_passed','full_regression_passed',
                 'fault_lab_passed','secret_scan_green','independent_reviewer_approved',
                 'requested_live_trade','risk_veto_runtime_certified',
                 'authentic_exchange_data_certified'):
        if type(getattr(evidence,name)) is not bool:
            raise TypeError('boolean evidence fields must be actual bools')
    if (not isinstance(evidence.python_ci_green, tuple) or
        any(not isinstance(s,str) or s not in SUPPORTED_CI for s in evidence.python_ci_green)):
        raise ValueError('invalid Python CI evidence')
    notes=[]
    if not evidence.phase03_git_source_verified:
        notes.append('BASE_GIT_SOURCE_NOT_VERIFIED')
    if not evidence.focused_tests_passed:
        notes.append('FOCUSED_TESTS_NOT_GREEN')
    if not evidence.full_regression_passed:
        notes.append('FULL_REGRESSION_NOT_GREEN')
    if not evidence.fault_lab_passed:
        notes.append('FAULT_LAB_NOT_GREEN')
    ready=not notes
    ci_ok=tuple(sorted(set(evidence.python_ci_green)))==SUPPORTED_CI
    if not ci_ok:
        notes.append('PHASE04_MULTI_PYTHON_CI_PENDING')
    if not evidence.secret_scan_green:
        notes.append('PHASE04_SECRET_SCAN_PENDING')
    if not evidence.independent_reviewer_approved:
        notes.append('INDEPENDENT_REVIEW_PENDING')
    if evidence.requested_live_trade:
        notes.append('LIVE_TRADING_REQUEST_DENIED')
    notes.append('NO_AUTHENTIC_LIVE_MARKET_VALIDATION')
    notes.append('INDEPENDENT_RISK_VETO_NOT_RUNTIME_CERTIFIED')
    review_ready=ready and ci_ok and evidence.secret_scan_green and evidence.independent_reviewer_approved
    verdict = ('DRAFT_PR_REVIEW_READY' if review_ready else
               'OFFLINE_RESEARCH_CANDIDATE' if ready else 'NO_GO')
    return GuardianReleaseDecision(ready, review_ready, False, False, verdict, tuple(notes))
