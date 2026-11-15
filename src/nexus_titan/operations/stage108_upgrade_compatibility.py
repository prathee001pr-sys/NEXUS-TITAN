"""Stage108: read-only continuity contract across Stage104–107.

Adopts *ideas* from Bhav/Nautilus/LEAN/Qlib/RD-Agent/Jesse; no external code,
network, credentials, venue or production policy is imported or executed.
Hashes prove local input equality, not independent market authenticity.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .stage104_historical_catalog_review import Stage104Catalog
from .stage105_execution_stress_review import Stage105ExecutionPreview
from .stage106_holdout_research_gate import Stage106ResearchReview
from .stage107_adversarial_assurance_review import Stage107AdversarialReview, SCENARIOS


class Stage108Blocked(ValueError):
    """An upstream capability, lineage or isolation boundary failed."""


_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REFERENCES = ("BHAV_FO_DATA_COST", "NAUTILUS_EXECUTION", "LEAN_OPTIONS_LIFECYCLE",
               "QLIB_RESEARCH", "RD_AGENT_RESEARCH", "JESSE_ROBUSTNESS")


@dataclass(frozen=True, slots=True)
class Stage108Compatibility:
    symbol: str
    india_currency: str
    crypto_currency: str
    catalog_sha256: str
    execution_sha256: str
    holdout_sha256: str
    adversarial_sha256: str
    reference_names: tuple[str, ...]
    compatibility_sha256: str
    duplicate_execution_engine_added: bool = False
    third_party_code_imported: bool = False
    independent_market_source_verified: bool = False
    risk_veto_runtime_certified: bool = False
    live_trading_enabled: bool = False
    strategy_promotion_enabled: bool = False
    verdict: str = "ADDITIVE_SYNTHETIC_COMPATIBILITY_ONLY_NO_GO"


def review_stage108_compatibility(
    catalog: Stage104Catalog,
    execution: Stage105ExecutionPreview,
    research: Stage106ResearchReview,
    adversarial: Stage107AdversarialReview,
) -> Stage108Compatibility:
    if (type(catalog) is not Stage104Catalog or type(execution) is not Stage105ExecutionPreview
        or type(research) is not Stage106ResearchReview
        or type(adversarial) is not Stage107AdversarialReview):
        raise Stage108Blocked("Exact typed predecessor reports are required")
    if (catalog.symbol not in ("NIFTY", "BANKNIFTY") or catalog.symbol != execution.underlying
        or catalog.symbol != research.symbol or catalog.symbol != adversarial.underlying
        or catalog.currency != execution.currency or catalog.currency != research.currency
        or catalog.currency != "INR" or adversarial.india_currency != "INR"
        or adversarial.crypto_currency != "USDT"
        or research.holdout_catalog_sha256 != catalog.catalog_sha256
        or execution.catalog_sha256 != catalog.catalog_sha256
        or research.stage105_scenario_sha256 != execution.scenario_sha256
        or adversarial.stage104_sha256 != catalog.catalog_sha256
        or adversarial.stage105_sha256 != execution.scenario_sha256
        or adversarial.stage106_sha256 != research.evidence_sha256
        or adversarial.stage103_sha256 != research.stage103_review_sha256
        or catalog.independent_data_provider_verified is not False
        or catalog.complete_trading_calendar_verified is not False
        or catalog.historical_15y_coverage_verified is not False
        or catalog.strategy_signal_authorized is not False
        or catalog.live_trading_enabled is not False
        or catalog.verdict != "SYNTHETIC_CATALOG_STRUCTURE_ONLY_NO_GO"
        or execution.actual_fill_verified is not False
        or execution.statutory_charges_verified is not False
        or execution.execution_liquidity_verified is not False
        or execution.trade_authorized is not False
        or execution.live_trading_enabled is not False
        or execution.verdict != "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO"
        or research.lookahead_window_overlap is not False
        or research.out_of_sample_market_evidence_verified is not False
        or research.real_accuracy_verified is not False
        or research.autonomous_strategy_promotion is not False
        or research.live_trading_enabled is not False
        or research.verdict != "SYNTHETIC_HOLDOUT_STRUCTURE_ONLY_NO_GO"
        or adversarial.actual_independent_veto_verified is not False
        or adversarial.production_risk_policy_certified is not False
        or adversarial.market_source_verified is not False
        or adversarial.real_security_audit_completed is not False
        or adversarial.shadow_trading_verified is not False
        or adversarial.live_trading_enabled is not False
        or adversarial.automated_promotion_approved is not False
        or adversarial.verdict != "DECLARED_SYNTHETIC_NEGATIVE_FIXTURES_ONLY_NO_GO"
        or adversarial.synthetic_negative_case_count != len(SCENARIOS)
        or type(adversarial.negative_scenarios) is not tuple
        or adversarial.negative_scenarios != tuple(sorted(SCENARIOS))):
        raise Stage108Blocked("Mismatched report lineage or unsafe capability promotion")
    hashes = (catalog.catalog_sha256, execution.scenario_sha256,
              research.evidence_sha256, adversarial.review_sha256,
              research.stage103_review_sha256)
    if not all(type(h) is str and _HASH.fullmatch(h) for h in hashes):
        raise Stage108Blocked("Invalid report fingerprints")
    payload = ["STAGE108_COMPATIBILITY_V1", catalog.symbol, *hashes, list(_REFERENCES)]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage108Compatibility(catalog.symbol, "INR", "USDT", *hashes[:4],
                                  _REFERENCES, digest)
