"""Stage111: isolated Phase-01 research/fee/replay compatibility join.

This is **not** an operational or strategy-promotion approval. The signed hash
is a local deterministic fingerprint only. Does not execute proposed code.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from datetime import date

from .stage108_upgrade_compatibility import Stage108Compatibility
from .stage109_effective_dated_stt import Stage109CostPreview, SOURCE, CUTOFF
from .stage110_deterministic_execution_replay import Stage110ExecutionReplay
from .stage105_execution_stress_review import Stage105ExecutionPreview


class Stage111Blocked(ValueError):
    pass


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class Stage111ResearchProposal:
    experiment_id: str
    proposed_code_sha256: str
    dataset_sha256: str
    fixed_seed: int
    state: str = "PROPOSED"  # PROPOSED or REJECTED; no approval path
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    autonomous_promotion_enabled: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage111Phase01Report:
    symbol: str
    indian_currency: str
    crypto_currency: str
    experiment_id: str
    filled_quantity: int
    turnover_paise: int
    modeled_stt_paise: int
    modeled_total_charges_paise: int
    modeled_cash_delta_paise: int
    stage108_sha256: str
    stage109_sha256: str
    stage110_sha256: str
    report_sha256: str
    independent_market_data_verified: bool = False
    real_market_execution_verified: bool = False
    independent_risk_veto_runtime_certified: bool = False
    exchange_fee_breakdown_verified: bool = False
    strategy_promotion_enabled: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "PHASE01_SYNTHETIC_INTEGRATION_ONLY_NO_GO"


def review_stage111_phase01(
    compatibility: Stage108Compatibility,
    execution_preview: Stage105ExecutionPreview,
    costs: Stage109CostPreview,
    replay: Stage110ExecutionReplay,
    proposal: Stage111ResearchProposal,
) -> Stage111Phase01Report:
    if (type(compatibility) is not Stage108Compatibility
        or type(execution_preview) is not Stage105ExecutionPreview
        or type(costs) is not Stage109CostPreview
        or type(replay) is not Stage110ExecutionReplay
        or type(proposal) is not Stage111ResearchProposal):
        raise Stage111Blocked("Exact Phase01 typed reports required")
    checks = (
        compatibility.verdict == "ADDITIVE_SYNTHETIC_COMPATIBILITY_ONLY_NO_GO",
        compatibility.india_currency == "INR", compatibility.crypto_currency == "USDT",
        compatibility.duplicate_execution_engine_added is False,
        compatibility.third_party_code_imported is False,
        compatibility.independent_market_source_verified is False,
        compatibility.risk_veto_runtime_certified is False,
        compatibility.live_trading_enabled is False,
        compatibility.strategy_promotion_enabled is False,
        compatibility.symbol in ("NIFTY", "BANKNIFTY"),
        type(compatibility.reference_names) is tuple and len(compatibility.reference_names)==6,
        execution_preview.underlying == compatibility.symbol,
        execution_preview.currency == "INR",
        compatibility.catalog_sha256 == execution_preview.catalog_sha256,
        compatibility.execution_sha256 == execution_preview.scenario_sha256,
        execution_preview.verdict == "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO",
        execution_preview.actual_fill_verified is False,
        execution_preview.trade_authorized is False,
        execution_preview.live_trading_enabled is False,
        replay.verdict == "SYNTHETIC_EVENT_REPLAY_ONLY_NO_GO",
        replay.evidence_tier == "SYNTHETIC_L1",
        replay.real_order_book_verified is False,
        replay.real_exchange_fill_verified is False,
        replay.independent_risk_veto_verified is False,
        replay.trade_authorized is False,
        replay.live_trading_enabled is False,
        replay.stage105_scenario_sha256 == execution_preview.scenario_sha256,
        replay.request_id == execution_preview.request_id,
        replay.contract_id == execution_preview.contract_id,
        replay.side == execution_preview.side,
        replay.requested_quantity == execution_preview.requested_quantity,
        replay.filled_quantity <= execution_preview.filled_quantity,
        replay.filled_quantity >= 0,
        replay.unfilled_quantity == replay.requested_quantity - replay.filled_quantity,
        costs.verdict == "DATED_STT_ESTIMATE_ONLY_NO_GO",
        costs.instrument == "OPTION_PREMIUM",
        costs.side == replay.side,
        costs.quantity == replay.filled_quantity,
        costs.rate_source == SOURCE,
        costs.taxable_value_paise == (costs.turnover_paise if costs.side == "SELL" else 0),
        costs.other_modeled_charges_paise >= 0,
        costs.modeled_total_charges_paise == costs.modeled_stt_paise + costs.other_modeled_charges_paise,
        costs.turnover_paise == replay.modeled_turnover_paise,
        costs.intrinsic_value_paise == 0,
        costs.actual_broker_charges_verified is False,
        costs.exchange_rounding_verified is False,
        costs.trade_authorized is False,
        costs.live_trading_enabled is False,
        costs.modeled_total_charges_paise >= costs.modeled_stt_paise >= 0,
        proposal.state in ("PROPOSED", "REJECTED"),
        proposal.source == "LOCAL_SYNTHETIC_TEST_ONLY",
        proposal.dataset_sha256 == compatibility.catalog_sha256,
        proposal.autonomous_promotion_enabled is False,
        proposal.live_trading_enabled is False,
        type(proposal.fixed_seed) is int and 0 <= proposal.fixed_seed <= 2**32-1,
        type(proposal.experiment_id) is str and bool(_ID.fullmatch(proposal.experiment_id)),
    )
    if not all(checks):
        raise Stage111Blocked("Synthetic audit, money or authority boundary mismatch")
    try:
        cost_date = date.fromisoformat(costs.trading_date)
    except (ValueError, TypeError, AttributeError) as exc:
        raise Stage111Blocked("Unparseable cost date") from exc
    if not isinstance(costs.trading_date, str) or costs.trading_date != cost_date.isoformat():
        raise Stage111Blocked("Noncanonical cost date")
    rate = (1500 if cost_date >= CUTOFF else 1000) if costs.side == "SELL" and costs.quantity else 0
    expected_stt = (costs.taxable_value_paise * rate + 999_999) // 1_000_000
    if (costs.stt_rate_ppm != rate or costs.modeled_stt_paise != expected_stt):
        raise Stage111Blocked("Invalid modeled statutory STT rate or arithmetic")
    if (execution_preview.source_last_asof_ist[:10] != costs.trading_date
        or not all(type(h) is str and _HASH.fullmatch(h) for h in (
            compatibility.compatibility_sha256, costs.source_sha256, replay.replay_sha256,
            proposal.dataset_sha256, proposal.proposed_code_sha256))):
        raise Stage111Blocked("Unlinked research date or malformed fingerprints")
    if (replay.filled_quantity == 0 and replay.modeled_turnover_paise != 0):
        raise Stage111Blocked("Zero-fill has nonzero turnover")
    cash = (-1 if replay.side == "BUY" else 1) * replay.modeled_turnover_paise - costs.modeled_total_charges_paise
    payload = ["STAGE111_PHASE01_SYNTHETIC_V1", compatibility.compatibility_sha256,
               costs.source_sha256, replay.replay_sha256, proposal.experiment_id,
               proposal.proposed_code_sha256, proposal.dataset_sha256, proposal.fixed_seed,
               proposal.state, cash]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage111Phase01Report(compatibility.symbol, "INR", "USDT",
        proposal.experiment_id, replay.filled_quantity, replay.modeled_turnover_paise,
        costs.modeled_stt_paise, costs.modeled_total_charges_paise, cash,
        compatibility.compatibility_sha256, costs.source_sha256, replay.replay_sha256, digest)


def review_stage111_pipeline(
    catalog, execution_preview, holdout_research, adversarial,
    replay_intent, replay_events, proposal,
    other_charges=None,
) -> Stage111Phase01Report:
    """One explicit read-only integration entry point for Stage108→111.

    Failures propagate from strict predecessor checks. No data fetching,
    mutation, execution venue, agent coding, strategy promotion or order path.
    """
    from .stage108_upgrade_compatibility import review_stage108_compatibility
    from .stage109_effective_dated_stt import (
        Stage109SyntheticTrade, Stage109OtherCharges, review_stage109_cost)
    from .stage110_deterministic_execution_replay import review_stage110_execution

    compatibility = review_stage108_compatibility(
        catalog, execution_preview, holdout_research, adversarial)
    replay = review_stage110_execution(execution_preview, replay_intent, replay_events)
    charges = Stage109OtherCharges() if other_charges is None else other_charges
    trade = Stage109SyntheticTrade(
        execution_preview.source_last_asof_ist[:10], "OPTION_PREMIUM", replay.side,
        replay.filled_quantity, replay.modeled_turnover_paise)
    costs = review_stage109_cost(trade, charges)
    return review_stage111_phase01(compatibility, execution_preview, costs, replay, proposal)
