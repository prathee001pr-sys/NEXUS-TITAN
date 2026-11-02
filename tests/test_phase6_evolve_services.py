import tempfile
import unittest
from pathlib import Path

from nexus_titan.self_improvement import (
    AgentCreationEngine, EvolutionAgentCoordinator, LearningStore,
    MarketRegimeDetector, ResearchDocument, ResearchIngestionService,
    StrategyEvidenceRegistry, TitanEvolveEngine,
)


class EvolveServicesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/"evolve.db"
        self.engine=TitanEvolveEngine(LearningStore(self.db))

    def tearDown(self):
        self.temp.cleanup()

    def test_research_ingestion_is_provenance_backed(self):
        record=ResearchIngestionService(self.engine).ingest_document(
            ResearchDocument("Volatility research","ATR measures volatility.",
                             "manual:paper-1","market-regime"),
            tags=("atr",))
        self.assertEqual(record.confidence,0.45)
        self.assertIn("UNTRUSTED_EXTERNAL_EVIDENCE",record.evidence)
        self.assertIn("untrusted-source",record.tags)

    def test_allowlisted_fetcher_rejects_untrusted_hosts(self):
        from nexus_titan.self_improvement import AllowlistedHTTPSResearchSource
        source=AllowlistedHTTPSResearchSource({"example.org"})
        with self.assertRaises(ValueError):
            source._validate_url("http://example.org/file")
        with self.assertRaises(PermissionError):
            source._validate_url("https://other.example/file")

    def test_market_regime_and_minimum_sample_gate(self):
        detector=MarketRegimeDetector(lookback=10)
        unknown=detector.classify([{"close":100.0}]*5)
        self.assertEqual(unknown.name,"UNKNOWN")
        candles=[{"close":100.0+i} for i in range(11)]
        regime=detector.classify(candles)
        self.assertEqual(regime.name,"TRENDING_UP")
        registry=StrategyEvidenceRegistry(self.db)
        registry.record("ema","TRENDING_UP",12,2.0,1.0,0.8,"walk-forward:test")
        self.assertEqual(registry.recommend("TRENDING_UP").status,"NO_RECOMMENDATION")

    def test_evidence_registry_candidate_still_requires_review(self):
        registry=StrategyEvidenceRegistry(self.db)
        registry.record("ema","TRENDING_UP",35,2.0,1.0,0.8,"walk-forward:test")
        rec=registry.recommend("TRENDING_UP",min_observations=30)
        self.assertEqual(rec.status,"RESEARCH_CANDIDATE")
        self.assertIn("human approval",rec.explanation.lower())

    def test_agent_creation_requires_explicit_human_approval(self):
        creator=AgentCreationEngine(self.db,existing_agent_ids=("EVOLUTION_MANAGER",))
        record=creator.create_prototype({
            "agent_id":"MARKET_RESEARCHER","name":"Market Researcher",
            "purpose":"Research only.","capabilities":["research"],
            "tools":["approved_research_sources"],"inputs":["approved_data"],
            "outputs":["research_notes"],"coordination_with":["EVOLUTION_MANAGER"],
            "acceptance_criteria":["Sources are cited."],
        })
        self.assertEqual(record.status,"SANDBOX_PASSED")
        self.assertEqual(creator.list_registry(),[])
        result=creator.review_and_register(record.creation_id,approved=True,approved_by="Owner")
        self.assertEqual(result.status,"APPROVED_REGISTERED")

    def test_coordinator_runs_twelve_supervised_agents(self):
        outcomes=EvolutionAgentCoordinator(self.engine).run_cycle()
        self.assertEqual(len(outcomes),12)
        status=EvolutionAgentCoordinator(self.engine).status()
        self.assertFalse(status["live_orders_allowed"])
        self.assertFalse(status["generated_code_execution_allowed"])


if __name__=="__main__":
    unittest.main()
