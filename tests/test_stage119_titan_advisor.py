from dataclasses import FrozenInstanceError
import pytest
from nexus_titan.operations.stage119_titan_advisor import (AdvisorContext, AdvisorFeedbackLedger,
    recommend_best_use,recommend_with_feedback)

def test_default_prioritizes_real_blockers():
    a=recommend_best_use(AdvisorContext(),max_items=8)
    assert a and len(a)<=8
    assert a[0].urgency=='P0' and 'Crash' in a[0].title
    assert any('data' in s.title.lower() for s in a)
    assert all(s.needs_user_approval and not s.order_or_code_executed and not s.estimated_gain_verified for s in a)
    assert all(s.next_step and s.i_can_help_by and s.improvement_goal for s in a)

def test_verified_context_suppresses_unneeded_advice():
    ctx=AdvisorContext(guardian_tested=True,ci_verified=True,market_data_verified=True,fo_engine_verified=True,
      oos_verified=True,risk_veto_verified=True,learning_evidence_count=3,champion_challenger_verified=True,
      phone_first=False)
    assert recommend_best_use(ctx)==()

def test_feedback_dismissal_and_interest(tmp_path):
    ctx=AdvisorContext()
    advice=recommend_best_use(ctx,max_items=8)
    db=AdvisorFeedbackLedger(tmp_path/'feedback.sqlite')
    try:
        db.record(advice[0],decision='DISMISSED',note='Handled separately')
        db.record(advice[-1],decision='INTERESTED')
        ordered=recommend_with_feedback(ctx,db,max_items=7)
        assert advice[0].suggestion_id not in {x.suggestion_id for x in ordered}
        assert ordered[0].suggestion_id==advice[-1].suggestion_id
    finally:db.close()

def test_only_supported_goal_and_binary_flags():
    with pytest.raises(ValueError):AdvisorContext(goal='autonomous_live_trading')
    with pytest.raises(ValueError):AdvisorContext(market_data_verified='yes')
    with pytest.raises(ValueError):AdvisorContext(learning_evidence_count=-1)
    with pytest.raises(ValueError):recommend_best_use(AdvisorContext(),max_items=0)

def test_immutable_advice():
    a=recommend_best_use(AdvisorContext())[0]
    with pytest.raises(FrozenInstanceError):a.order_or_code_executed=True
