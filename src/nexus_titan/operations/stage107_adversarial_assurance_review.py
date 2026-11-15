"""Stage107: synthetic adversarial evidence matrix (non-certifying).

A declaration that a negative *fixture* was blocked is NOT proof that the
actual independent Risk & Veto runtime blocks orders. The result always says
NO_GO, and does not mint permissions, attest real security or execute orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from .stage103_readonly_assurance_gate import Stage103AssuranceReport
from .stage104_historical_catalog_review import Stage104Catalog
from .stage105_execution_stress_review import Stage105ExecutionPreview
from .stage106_holdout_research_gate import Stage106ResearchReview

class Stage107Blocked(ValueError):
    pass

SCENARIOS = frozenset({
    "STALE_MARKET_DATA", "DUPLICATE_ORDER_ID", "EMERGENCY_KILL",
    "RESTART_REPLAY", "CROSS_CURRENCY", "INDEPENDENT_VETO", "MISSING_EXCHANGE_EVIDENCE",
})
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)

@dataclass(frozen=True, slots=True)
class Stage107SyntheticNegativeCase:
    scenario: str
    rejection_observed: bool
    fixture_sha256: str
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"

@dataclass(frozen=True, slots=True)
class Stage107AdversarialReview:
    underlying: str
    india_currency: str
    crypto_currency: str
    stage103_sha256: str
    stage104_sha256: str
    stage105_sha256: str
    stage106_sha256: str
    negative_scenarios: tuple[str, ...]
    synthetic_negative_case_count: int
    review_sha256: str
    actual_independent_veto_verified: bool = False
    production_risk_policy_certified: bool = False
    market_source_verified: bool = False
    real_security_audit_completed: bool = False
    shadow_trading_verified: bool = False
    live_trading_enabled: bool = False
    automated_promotion_approved: bool = False
    verdict: str = "DECLARED_SYNTHETIC_NEGATIVE_FIXTURES_ONLY_NO_GO"


def review_stage107_adversarial(
    assurance: Stage103AssuranceReport,
    catalog: Stage104Catalog,
    execution: Stage105ExecutionPreview,
    research: Stage106ResearchReview,
    cases: list[Stage107SyntheticNegativeCase] | tuple[Stage107SyntheticNegativeCase, ...],
) -> Stage107AdversarialReview:
    if (type(assurance) is not Stage103AssuranceReport or type(catalog) is not Stage104Catalog
        or type(execution) is not Stage105ExecutionPreview or type(research) is not Stage106ResearchReview
        or type(cases) not in (tuple, list) or len(cases) != len(SCENARIOS)):
        raise Stage107Blocked("Exact typed upstream outputs and complete bounded scenario matrix required")
    if (assurance.underlying != catalog.symbol or assurance.underlying != execution.underlying
        or assurance.underlying != research.symbol or catalog.currency != "INR"
        or execution.currency != "INR" or research.currency != "INR"
        or assurance.indian_currency != "INR" or assurance.crypto_currency != "USDT"
        or assurance.synthetic_inputs_consistent is not True
        or assurance.source_authenticity_verified is not False
        or assurance.real_market_shadow_verified is not False
        or assurance.trade_authorized is not False or assurance.live_trading_enabled is not False
        or assurance.verdict != "CROSS_STAGE_SYNTHETIC_INTEGRITY_ONLY_NO_GO"
        or catalog.independent_data_provider_verified is not False
        or catalog.complete_trading_calendar_verified is not False
        or catalog.historical_15y_coverage_verified is not False
        or catalog.strategy_signal_authorized is not False or catalog.live_trading_enabled is not False
        or catalog.verdict != "SYNTHETIC_CATALOG_STRUCTURE_ONLY_NO_GO"
        or execution.catalog_sha256 != catalog.catalog_sha256
        or execution.chain_sha256 != assurance.synthetic_chain_sha256
        or execution.window_sha256 != assurance.historical_window_sha256
        or execution.trade_authorized is not False or execution.actual_fill_verified is not False
        or execution.live_trading_enabled is not False
        or execution.verdict != "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO"
        or research.holdout_catalog_sha256 != catalog.catalog_sha256
        or research.stage103_review_sha256 != assurance.review_sha256
        or research.stage105_scenario_sha256 != execution.scenario_sha256
        or research.real_accuracy_verified is not False
        or research.autonomous_strategy_promotion is not False
        or research.live_trading_enabled is not False
        or research.verdict != "SYNTHETIC_HOLDOUT_STRUCTURE_ONLY_NO_GO"):
        raise Stage107Blocked("Upstream evidence, isolation, no-live, or governance boundary failed")
    for h in (assurance.review_sha256, catalog.catalog_sha256, execution.scenario_sha256,
              research.evidence_sha256, research.training_catalog_sha256):
        if type(h) is not str or not _HASH.fullmatch(h):
            raise Stage107Blocked("Stage fingerprints must be lowercase SHA-256")
    seen: set[str] = set()
    normalized: list[list[str]] = []
    for c in cases:
        if (type(c) is not Stage107SyntheticNegativeCase
            or type(c.scenario) is not str or c.scenario not in SCENARIOS
            or c.scenario in seen or c.rejection_observed is not True
            or c.source != "LOCAL_SYNTHETIC_TEST_ONLY"
            or type(c.fixture_sha256) is not str or not _HASH.fullmatch(c.fixture_sha256)):
            raise Stage107Blocked("Missing, duplicate, unverified, or non-blocking synthetic scenario")
        seen.add(c.scenario)
        normalized.append([c.scenario, c.fixture_sha256])
    if seen != SCENARIOS:
        raise Stage107Blocked("Adversarial scenario coverage incomplete")
    normalized.sort()
    payload = ["STAGE107_DECLARED_NEGATIVE_FIXTURES_V1", assurance.review_sha256,
               catalog.catalog_sha256, execution.scenario_sha256, research.evidence_sha256, normalized]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage107AdversarialReview(assurance.underlying, "INR", "USDT", assurance.review_sha256,
        catalog.catalog_sha256, execution.scenario_sha256, research.evidence_sha256,
        tuple(sorted(seen)), len(seen), digest)
