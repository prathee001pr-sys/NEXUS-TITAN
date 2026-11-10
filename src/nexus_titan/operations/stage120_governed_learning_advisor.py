"""No-live research bridge: source-linked learning -> governed proposal -> best-use advice.

The bridge does not execute/backtest/publish code. User-authored candidate rules are
recorded as untrusted hypotheses for future independent evaluation only.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from nexus_titan.evolve.governance import GovernedEvolveService
from nexus_titan.operations.stage118_titan_learn import LearningEvidenceLibrary
from nexus_titan.operations.stage119_titan_advisor import AdvisorContext, AdvisorSuggestion, recommend_best_use


@dataclass(frozen=True, slots=True)
class ProposedLearningExperiment:
    experiment_id: str
    source_id: str
    evidence_id: str
    citation_anchor: str
    hypothesis_digest: str
    status: str = 'PROPOSED'
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    strategy_promotion_enabled: bool = False


def propose_learning_hypothesis(
    library: LearningEvidenceLibrary,
    governance: GovernedEvolveService,
    *, evidence_id: str, entry_rule: str, exit_rule: str,
    risk_rule: str, instrument: str, timeframe: str,
) -> ProposedLearningExperiment:
    if not isinstance(library, LearningEvidenceLibrary) or not isinstance(governance, GovernedEvolveService):
        raise TypeError('real learning library and governed research service required')
    evidence = library.get(evidence_id)
    def bounded(value: str, name: str) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 280:
            raise ValueError(f'invalid {name}')
        return value.strip()
    payload = {k: bounded(v,k) for k,v in {
        'entry':entry_rule, 'exit':exit_rule, 'risk':risk_rule,
        'instrument':instrument, 'timeframe':timeframe,
    }.items()}
    statement = ('UNVERIFIED RESEARCH HYPOTHESIS ONLY; source=' + evidence.source_id +
        '; citation=' + evidence.citation_anchor +
        '; instrument=' + payload['instrument'] + '; timeframe=' + payload['timeframe'] +
        '; entry=' + payload['entry'] + '; exit=' + payload['exit'] + '; risk=' + payload['risk'])
    exp = governance.propose(name='Learning hypothesis '+evidence.evidence_id[:12],
                             hypothesis=statement, target='strategy_research')
    return ProposedLearningExperiment(exp.experiment_id, evidence.source_id, evidence.evidence_id,
                                      evidence.citation_anchor, hashlib.sha256(statement.encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class LearningAdvisorReview:
    learned_evidence_count: int
    proposed_experiments: int
    suggestions: tuple[AdvisorSuggestion, ...]
    verdict: str = 'READ_ONLY_RESEARCH_CANDIDATE_NO_GO'
    code_execution_enabled: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    strategy_promotion_enabled: bool = False


def review_learning_and_advisor(library: LearningEvidenceLibrary,
                                governance: GovernedEvolveService, *, context: AdvisorContext) -> LearningAdvisorReview:
    if not isinstance(library, LearningEvidenceLibrary) or not isinstance(governance, GovernedEvolveService):
        raise TypeError('valid library and governed research service required')
    count = library.db.execute('SELECT COUNT(*) FROM titan_learning_evidence').fetchone()[0]
    if context.learning_evidence_count != count:
        raise ValueError('context and library evidence count mismatch')
    return LearningAdvisorReview(count, governance.snapshot().experiment_count, recommend_best_use(context))
