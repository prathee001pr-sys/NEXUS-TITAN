"""Stage124 source/CI/risk boundary acceptance tests."""
from dataclasses import FrozenInstanceError, replace
import pytest
from nexus_titan.operations.stage124_guardian_release_gate import (
    GuardianReleaseEvidence, review_guardian_release)

GOOD=GuardianReleaseEvidence(True,True,True,True)


def test_local_green_is_not_ci_or_trade_approval():
    out=review_guardian_release(GOOD)
    assert out.research_candidate_ready and out.verdict=='OFFLINE_RESEARCH_CANDIDATE'
    assert not out.draft_pr_review_ready and not out.trade_authorized
    assert 'PHASE04_MULTI_PYTHON_CI_PENDING' in out.reasons

@pytest.mark.parametrize('field', ['phase03_git_source_verified','focused_tests_passed',
                                    'full_regression_passed','fault_lab_passed'])
def test_any_local_gate_failure_denies_research(field):
    out=review_guardian_release(replace(GOOD,**{field:False}))
    assert out.verdict=='NO_GO' and not out.research_candidate_ready


def test_full_ci_and_review_only_enable_draft_review():
    e=replace(GOOD,python_ci_green=('3.11','3.12','3.13'),secret_scan_green=True,
              independent_reviewer_approved=True)
    out=review_guardian_release(e)
    assert out.draft_pr_review_ready and out.verdict=='DRAFT_PR_REVIEW_READY'
    assert not out.trade_authorized and not out.automatic_strategy_promotion


def test_even_fake_risk_and_data_flags_cannot_promote_live():
    e=replace(GOOD,python_ci_green=('3.11','3.12','3.13'),secret_scan_green=True,
              independent_reviewer_approved=True,requested_live_trade=True,
              risk_veto_runtime_certified=True,authentic_exchange_data_certified=True)
    out=review_guardian_release(e)
    assert not out.trade_authorized and not out.automatic_strategy_promotion
    assert 'LIVE_TRADING_REQUEST_DENIED' in out.reasons


@pytest.mark.parametrize('field', ['focused_tests_passed','phase03_git_source_verified',
                                    'full_regression_passed','fault_lab_passed','secret_scan_green',
                                    'independent_reviewer_approved','requested_live_trade',
                                    'risk_veto_runtime_certified','authentic_exchange_data_certified'])
def test_non_boolean_evidence_rejected(field):
    with pytest.raises(TypeError):review_guardian_release(replace(GOOD,**{field:1}))

@pytest.mark.parametrize('ci',[('3.11','bogus'),['3.11','3.12','3.13'],('3.14',),('3.13',None)])
def test_untrusted_ci_evidence_rejected(ci):
    with pytest.raises((TypeError,ValueError)):
        review_guardian_release(replace(GOOD,python_ci_green=ci))


def test_wrong_type_rejected():
    with pytest.raises(TypeError):review_guardian_release(dict())


def test_immutable_record():
    d=review_guardian_release(GOOD)
    with pytest.raises(FrozenInstanceError):d.trade_authorized=True


def test_partial_ci_not_ready():
    d=review_guardian_release(replace(GOOD,python_ci_green=('3.11','3.13'),secret_scan_green=True,
                                      independent_reviewer_approved=True))
    assert not d.draft_pr_review_ready
