from dataclasses import FrozenInstanceError
import pytest
from nexus_titan.evolve.governance import GovernedEvolveService
from nexus_titan.operations.stage118_titan_learn import LearningEvidenceLibrary
from nexus_titan.operations.stage119_titan_advisor import AdvisorContext
from nexus_titan.operations.stage120_governed_learning_advisor import (
    propose_learning_hypothesis,review_learning_and_advisor)


def test_source_to_research_proposal_is_never_promotion(tmp_path):
    with LearningEvidenceLibrary(tmp_path/'study.sqlite') as lib:
        e=lib.ingest_excerpt(kind='video_transcript',title='Risk video',reference='authorized notes',
                             rights='USER_OWNED',citation_anchor='time:00:01:50',
                             excerpt='Teacher claims short-term trend crossing works.')
        gov=GovernedEvolveService()
        result=propose_learning_hypothesis(lib,gov,evidence_id=e.evidence_id,
                                          entry_rule='signal=MA crossing',exit_rule='signal reversal',
                                          risk_rule='paper only 0.5 percent hypothetical cap',
                                          instrument='NIFTY',timeframe='5m')
        assert result.status=='PROPOSED' and result.source_id==e.source_id
        assert not result.live_trading_enabled and not result.trade_authorized and not result.strategy_promotion_enabled
        assert gov.research.get(result.experiment_id).status.value=='proposed'
        assert not gov.snapshot().code_execution_enabled
        with pytest.raises(FrozenInstanceError):result.trade_authorized=True
        report=review_learning_and_advisor(lib,gov,context=AdvisorContext(learning_evidence_count=1))
        assert report.learned_evidence_count==1 and report.proposed_experiments==1
        assert report.verdict.endswith('NO_GO') and not report.code_execution_enabled


def test_no_untrusted_source_or_missing_rule(tmp_path):
    with LearningEvidenceLibrary(tmp_path/'study.sqlite') as lib:
        gov=GovernedEvolveService()
        with pytest.raises(KeyError):propose_learning_hypothesis(lib,gov,evidence_id='x',
                                  entry_rule='a',exit_rule='b',risk_rule='c',instrument='NIFTY',timeframe='1m')
        evidence=lib.ingest_excerpt(kind='pdf',title='Test',reference='owned',rights='USER_OWNED',
            citation_anchor='page:1',excerpt='Look for higher highs')
        with pytest.raises(ValueError):propose_learning_hypothesis(lib,gov,evidence_id=evidence.evidence_id,
                              entry_rule=' ',exit_rule='b',risk_rule='c',instrument='NIFTY',timeframe='1m')
        with pytest.raises(ValueError):review_learning_and_advisor(lib,gov,context=AdvisorContext(learning_evidence_count=0))
