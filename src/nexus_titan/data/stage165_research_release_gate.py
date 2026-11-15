"""Stage 165: research-only evidence gate, never an order authorization."""
from dataclasses import dataclass
from .stage161_coverage_metrics import Coverage
from .stage162_fo_chain_consistency import ChainAudit
from .stage163_cost_assumptions import CostAudit
from .stage164_split_embargo import SplitAudit

@dataclass(frozen=True)
class ResearchGate:
    accepted_for_offline_research: bool
    blockers: tuple[str, ...]

def evaluate_research_gate(*, coverage: Coverage, chain: ChainAudit, costs: CostAudit,
                           split: SplitAudit, source_verified: bool, live_requested: bool = False) -> ResearchGate:
    checks={'coverage':isinstance(coverage,Coverage) and coverage.complete,
            'chain':isinstance(chain,ChainAudit) and chain.accepted,
            'costs':isinstance(costs,CostAudit) and costs.accepted,
            'split':isinstance(split,SplitAudit) and split.accepted,
            'source':source_verified is True,
            'live trading prohibited':live_requested is False}
    blockers=tuple(k for k,v in checks.items() if not v)
    return ResearchGate(not blockers,blockers)
