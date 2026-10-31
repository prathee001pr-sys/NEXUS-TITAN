"""TITAN EVOLVE: governed continuous learning and self-improvement."""
from .adaptive import (
    MarketRegime, MarketRegimeDetector, StrategyEvidenceRegistry, StrategyRecommendation,
)
from .agents import AgentOutcome, EvolutionAgentCoordinator, EvolutionAgentContext
from .agent_creation import AgentCreationEngine, AgentCreationRecord, AgentSpecification
from .agent_runtime import (
    AgentRuntime, AgentRuntimeError, AgentWorkflowCoordinator,
    RuntimeTaskResult, ToolExecutionContext, register_core_local_tools,
)
from .code_proposals import CodeChangeProposal, CodeChangeProposalManager
from .engine import (
    ExperimentResult, ImprovementProposal, LearningRecord, LearningStore,
    SkillVersion, TitanEvolveEngine,
)
from .experimentation import StrategyComparison, StrategyEvidence, StrategyExperimentRunner
from .llm_provider import LLMConfig, LLMProviderError, OpenAICompatibleProvider
from .llm_research import LLMResearchService
from .scheduler import (
    ResearchScheduleStore, ScheduledResearchResult, ScheduledResearchSource,
    ScheduledResearchWorker,
)
from .research_sources import (
    AllowlistedHTTPSResearchSource, ResearchDocument, ResearchIngestionService, ResearchSource,
)

__all__ = [
    "AgentCreationEngine", "AgentCreationRecord", "AgentSpecification",
    "AgentRuntime", "AgentRuntimeError", "AgentWorkflowCoordinator",
    "RuntimeTaskResult", "ToolExecutionContext", "register_core_local_tools",
    "AgentOutcome", "AllowlistedHTTPSResearchSource", "CodeChangeProposal",
    "CodeChangeProposalManager", "EvolutionAgentContext", "EvolutionAgentCoordinator",
    "ExperimentResult", "ImprovementProposal", "LearningRecord", "LearningStore",
    "LLMConfig", "LLMProviderError", "LLMResearchService", "OpenAICompatibleProvider",
    "MarketRegime", "MarketRegimeDetector", "ResearchDocument", "ResearchIngestionService",
    "ResearchScheduleStore", "ScheduledResearchResult", "ScheduledResearchSource",
    "ScheduledResearchWorker", "ResearchSource", "SkillVersion", "StrategyComparison",
    "StrategyEvidence", "StrategyEvidenceRegistry", "StrategyExperimentRunner",
    "StrategyRecommendation", "TitanEvolveEngine",
]
