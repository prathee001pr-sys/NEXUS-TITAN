"""Stage75: integrated NIFTY/BANKNIFTY F&O shadow-readiness research audit.

Composes Stage71-74 synthetic research evidence with Stage69's equity-only
risk preflight. Does not authorize paper orders, strategy promotion, broker
orders, or release. Operator-declared hashes and labels are not attestations.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from nexus_titan.data.stage71_fo_asof_alignment import Stage71FOLearningPreflight
from nexus_titan.derivatives.stage72_expiry_iv_research import Stage72OptionsResearchReport
from nexus_titan.evolve.stage73_fo_experience import FOEvolveReview
from nexus_titan.operations.stage69_risk_budget_preflight import Stage69ResearchPreflight
from nexus_titan.simulation.stage74_fo_options_scenario_lab import Stage74ScenarioResearchReport

_SHA = re.compile(r"[0-9a-fA-F]{64}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_EXTERNAL = (
    "CURRENT_MERGED_TREE_AND_OWNER_REVIEW_NOT_VERIFIED",
    "GLOBAL_UNBYPASSABLE_FO_RISK_GATE_NOT_VERIFIED",
    "ATOMIC_FO_CAPITAL_RESERVATIONS_NOT_VERIFIED",
    "LICENSED_EXCHANGE_MARKET_DATA_NOT_AUTHENTICATED",
    "REAL_EXECUTABLE_DEPTH_AND_FO_COSTS_NOT_VERIFIED",
    "PREDECLARED_SIGNED_FORWARD_SHADOW_TRIAL_NOT_VERIFIED",
    "INDEPENDENT_SECURITY_RECOVERY_AND_OWNER_APPROVAL_REQUIRED",
)


class Stage75ReadinessBlocked(ValueError):
    """Research inputs contradict safety invariants; no packet emitted."""


@dataclass(frozen=True, slots=True)
class Stage75VirtualResearchBudget:
    account_id: str
    virtual_capital_cents: int
    max_single_option_debit_bps: int = 2500
    max_scenario_loss_bps: int = 2000


@dataclass(frozen=True, slots=True)
class Stage75ReadinessCheck:
    name: str
    status: Literal["LOCAL_RESEARCH_PASS", "LOCAL_RESEARCH_BLOCKED", "EXTERNAL_MISSING"]
    detail: str


@dataclass(frozen=True, slots=True)
class Stage75FOShadowReadinessPacket:
    underlying: str
    option_symbol: str
    selected_strike: float
    selected_option_type: str
    source_stage71_sha256: str
    source_stage72_sha256: str
    stage73_review_sha256: str
    stage74_scenarios_sha256: str
    account_id: str
    virtual_capital_cents: int
    long_option_entry_debit_cents: int
    maximum_hypothetical_scenario_loss_cents: int
    option_debit_allocation_bps_rounded_up: int
    maximum_scenario_loss_bps_rounded_up: int
    research_budget_screen_passed: bool
    paired_oos_research_samples: int
    local_chain_structurally_consistent: bool
    checks: tuple[Stage75ReadinessCheck, ...]
    blockers: tuple[str, ...]
    research_packet_sha256: str
    # A local pass NEVER represents a real shadow-trading deployment permit.
    independently_authenticated_fo_source: bool = False
    independently_verified_forward_outcomes: bool = False
    official_margin_and_fees_verified: bool = False
    global_risk_veto_unbypassable: bool = False
    atomic_capital_book_verified: bool = False
    owner_approval_authenticated: bool = False
    real_shadow_trading_started: bool = False
    actual_fills_recorded: int = 0
    paper_order_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE75_FO_SHADOW_READINESS_RESEARCH_NO_GO"


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise Stage75ReadinessBlocked(name + " lacks valid SHA-256")
    return value.lower()


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Stage75ReadinessBlocked(name + " requires timezone-aware timestamp")
    return value.astimezone(timezone.utc)


def _deny_authority(obj: object, attrs: tuple[str, ...], label: str, count: str) -> None:
    if any(getattr(obj, x, None) is not False for x in attrs):
        raise Stage75ReadinessBlocked(label + " presents unauthorized verification")
    if type(getattr(obj, count, None)) is not int or getattr(obj, count) != 0:
        raise Stage75ReadinessBlocked(label + " presents nonzero broker order count")


def _rupee_cents(value: object, label: str) -> int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Stage75ReadinessBlocked(label + " must be finite")
    try:
        amount = Decimal(str(value))
        if amount < 0 or amount > Decimal("100000000000"):
            raise Stage75ReadinessBlocked(label + " must be bounded and nonnegative")
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise Stage75ReadinessBlocked(label + " not representable as cents") from exc
    return cents


def _ceil_bps(amount: int, capital: int) -> int:
    return (amount * 10000 + capital - 1) // capital


def inspect_stage75_fo_shadow_readiness(
    *,
    stage71: Stage71FOLearningPreflight,
    stage72: Stage72OptionsResearchReport,
    stage73: FOEvolveReview,
    stage74: Stage74ScenarioResearchReport,
    stage69: Stage69ResearchPreflight,
    budget: Stage75VirtualResearchBudget,
) -> Stage75FOShadowReadinessPacket:
    """Cross-check only a *single* long-option research idea, fail closed.

    The provided capital is a configurable research assumption. Stage69
    screens synthetic EQUITY_DELIVERY, NOT NSE F&O; its 'pass' is NOT an
    order, risk-gate, margin, or reservation authority for this packet.
    """
    types = (
        (stage71, Stage71FOLearningPreflight),
        (stage72, Stage72OptionsResearchReport),
        (stage73, FOEvolveReview),
        (stage74, Stage74ScenarioResearchReport),
        (stage69, Stage69ResearchPreflight),
        (budget, Stage75VirtualResearchBudget),
    )
    if any(not isinstance(actual, target) for actual, target in types):
        raise Stage75ReadinessBlocked("All six typed research records required")
    if (not isinstance(budget.account_id, str)
            or _ID.fullmatch(budget.account_id) is None
            or type(budget.virtual_capital_cents) is not int
            or not 100 <= budget.virtual_capital_cents <= 10**14
            or type(budget.max_single_option_debit_bps) is not int
            or not 1 <= budget.max_single_option_debit_bps <= 5000
            or type(budget.max_scenario_loss_bps) is not int
            or not 1 <= budget.max_scenario_loss_bps <= 5000):
        raise Stage75ReadinessBlocked("Invalid variable virtual-capital research limits")
    _deny_authority(stage71, (
        "vendor_identity_independently_authenticated", "data_licence_independently_authenticated",
        "point_in_time_exchange_contracts_authenticated", "independent_calendar_verified",
        "real_market_depth_verified", "historically_complete_fo_universe_verified",
        "leak_free_full_training_pipeline_verified", "model_performance_verified",
        "approved_for_strategy_promotion", "paper_order_authorized", "live_trading_enabled",
    ), "Stage71", "broker_orders_transmitted")
    _deny_authority(stage72, (
        "contract_master_independently_authenticated", "vendor_and_licence_independently_authenticated",
        "official_expiry_cutoff_authenticated", "tradeable_bid_ask_depth_verified",
        "model_calibration_or_accuracy_verified", "expiry_settlement_and_costs_verified",
        "strategy_promotion_authorized", "paper_order_authorized", "live_trading_enabled",
    ), "Stage72", "broker_orders_transmitted")
    _deny_authority(stage73, (
        "independent_exchange_data_verified", "independently_verified_outcomes",
        "real_oos_protocol_verified", "option_trade_pnl_verified",
        "model_weights_updated", "strategy_promotion_authorized",
        "paper_order_authorized", "live_trading_enabled",
    ), "Stage73", "broker_orders_transmitted")
    _deny_authority(stage74, (
        "real_exchange_data_authenticated", "official_cost_tariff_authenticated",
        "actual_market_depth_verified", "live_or_historical_fills_verified",
        "portfolio_margin_verified", "calibrated_stress_probabilities_verified",
        "actual_profitability_verified", "strategy_promotion_authorized",
        "paper_order_authorized", "live_trading_enabled",
    ), "Stage74", "broker_orders_transmitted")
    _deny_authority(stage69, (
        "caller_risk_telemetry_authenticated", "independently_authenticated_market_quote",
        "global_legacy_entrypoints_fenced", "single_atomic_authority_for_all_ledger_books",
        "risk_rechecked_at_real_fill", "authenticated_owner_approval",
        "budget_hold_performed", "order_submission_authorized",
        "strategy_promotion_authorized", "real_money_trading_enabled", "production_ready",
    ), "Stage69", "broker_orders_transmitted")
    if (stage71.verdict != "STAGE71_OFFLINE_ALIGNED_RESEARCH_ONLY_NO_GO"
            or stage72.release_verdict != "STAGE72_IV_GREEKS_RESEARCH_ONLY_NO_GO"
            or stage73.verdict != "STAGE73_RESEARCH_ONLY_NO_GO"
            or stage74.verdict != "STAGE74_OPTIONS_SCENARIO_RESEARCH_NO_GO"
            or stage69.verdict != "RESEARCH_ONLY_GLOBAL_RISK_NO_GO"):
        raise Stage75ReadinessBlocked("Research-only verdict drift")
    if (stage71.underlying not in ("NIFTY", "BANKNIFTY")
            or any(x != stage71.underlying for x in (
                stage72.underlying, stage74.underlying,
            )) or stage72.symbol != stage74.symbol):
        raise Stage75ReadinessBlocked("F&O underlying/symbol lineage mismatch")
    observed = _utc(stage72.observation_time, "Stage72 observation")
    if observed != _utc(stage74.observation_time, "Stage74 observation"):
        raise Stage75ReadinessBlocked("Stage72/74 observation timestamps differ")
    a71 = _sha(stage71.input_alignment_sha256, "Stage71 as-of join")
    a72 = _sha(stage72.source_alignment_sha256, "Stage72 as-of source")
    a74 = _sha(stage74.source_stage71_sha256, "Stage74 as-of source")
    s72 = _sha(stage72.research_output_sha256, "Stage72 output")
    s74 = _sha(stage74.source_stage72_sha256, "Stage74 Stage72 source")
    if a71 != a72 or a71 != a74 or s72 != s74:
        raise Stage75ReadinessBlocked("Cross-stage source digests disagree")
    opt_sha = _sha(stage72.source_option_sha256, "Stage72 option snapshot")
    if (type(stage71.aligned_observation_count) is not int
            or stage71.aligned_observation_count != len(stage71.observations)
            or not stage71.observations):
        raise Stage75ReadinessBlocked("Stage71 alignment count invalid")
    hits = [q for q in stage71.observations
            if (q.underlying == stage71.underlying
                and _utc(q.option_observed_at, "Stage71 option snapshot") == observed
                and _sha(q.option_snapshot_sha256, "Stage71 option source") == opt_sha)]
    if len(hits) != 1 or hits[0].futures_bar_closed_at.utcoffset() is None:
        raise Stage75ReadinessBlocked("Stage72 snapshot not uniquely present in Stage71 as-of evidence")
    matched = hits[0]
    if (_utc(matched.futures_bar_closed_at, "Stage71 futures closed") > observed
            or _utc(matched.futures_bar_opened_at, "Stage71 futures opened")
            >= _utc(matched.futures_bar_closed_at, "Stage71 futures closed")
            or type(matched.futures_age_seconds) is not int
            or matched.futures_age_seconds < 0
            or (observed - _utc(matched.futures_bar_closed_at, "Stage71 close")).total_seconds()
            != matched.futures_age_seconds):
        raise Stage75ReadinessBlocked("Stage71 futures bar look-ahead or age mismatch")
    if (not isinstance(stage74.outcomes, tuple) or not stage74.outcomes
            or len(stage74.outcomes) > 12
            or not isinstance(stage72.rows, tuple) or not stage72.rows):
        raise Stage75ReadinessBlocked("Stage72/74 research rows absent or oversized")
    first = stage74.outcomes[0]
    if (first.option_type not in ("CE", "PE") or type(first.lots) is not int
            or not 1 <= first.lots <= 100
            or type(first.quantity) is not int or first.quantity < 1
            or first.quantity > 100000
            or sum(r.strike == first.strike and r.option_type == first.option_type
                   for r in stage72.rows) != 1):
        raise Stage75ReadinessBlocked("Missing unique long option contract/stressed quantity")
    seen_cases: set[str] = set()
    debit: int | None = None
    largest_loss = 0
    for row in stage74.outcomes:
        if (not isinstance(row.case_name, str) or not row.case_name
                or row.case_name in seen_cases or len(row.case_name) > 80
                or row.strike != first.strike or row.option_type != first.option_type
                or row.quantity != first.quantity or row.lots != first.lots
                or row.independently_verified_depth_or_fill is not False
                or row.scenario_is_a_historical_backtest is not False):
            raise Stage75ReadinessBlocked("Stressed scenarios not a consistent research contract")
        seen_cases.add(row.case_name)
        entry = _rupee_cents(row.hypothetical_entry_debit_rupees, "Entry debit")
        premium = _rupee_cents(row.hypothetical_premium_at_risk_rupees, "Premium at risk")
        proceeds = _rupee_cents(row.hypothetical_exit_proceeds_rupees, "Exit proceeds")
        net = _rupee_cents(abs(row.hypothetical_round_trip_net_rupees), "Magnitude of model net")
        if (entry == 0 or entry != premium
                or abs((proceeds - entry) - (net if row.hypothetical_round_trip_net_rupees >= 0 else -net)) > 1
                or (debit is not None and entry != debit)):
            raise Stage75ReadinessBlocked("Hypothetical cashflow arithmetic or entry inconsistency")
        debit = entry
        largest_loss = max(largest_loss, entry - proceeds)
    if debit is None:
        raise Stage75ReadinessBlocked("No scenario debit")
    if (stage69.account_id != budget.account_id
            or not isinstance(stage69.blockers, tuple)
            or type(stage69.local_budget_integrity_checked) is not bool
            or type(stage69.local_synthetic_risk_screen_passed) is not bool):
        raise Stage75ReadinessBlocked("Stage69 synthetic equity reference/account mismatch")
    if (stage73.paired_count < 0 or stage73.unpaired_count < 0
            or stage73.unresolved_count < 0
            or type(stage73.research_review_suggested) is not bool
            or (stage73.research_review_suggested and
                (stage73.paired_count < 2
                 or stage73.challenger_minus_champion_brier is None
                 or stage73.challenger_minus_champion_brier >= 0))):
        raise Stage75ReadinessBlocked("Stage73 model review evidence inconsistent")
    r73 = _sha(stage73.review_sha256, "Stage73 OOS review")
    r74 = _sha(stage74.scenario_digest_sha256, "Stage74 scenario research")
    entry_bps = _ceil_bps(debit, budget.virtual_capital_cents)
    loss_bps = _ceil_bps(largest_loss, budget.virtual_capital_cents)
    local_budget_ok = (
        debit <= budget.virtual_capital_cents
        and entry_bps <= budget.max_single_option_debit_bps
        and loss_bps <= budget.max_scenario_loss_bps
    )
    checks = (
        Stage75ReadinessCheck("point_in_time_research_chain", "LOCAL_RESEARCH_PASS",
                              "Stage71->72->74 declared as-of/hash lineage matches"),
        Stage75ReadinessCheck("out_of_sample_model_review", "LOCAL_RESEARCH_PASS",
                              "Stage73 bounded OOS diagnostics observed; no independent labels"),
        Stage75ReadinessCheck("long_option_scenario_accounting", "LOCAL_RESEARCH_PASS",
                              "Stage74 scenario cashflow arithmetic internally consistent, not fills"),
        Stage75ReadinessCheck("variable_capital_stress_budget",
                              "LOCAL_RESEARCH_PASS" if local_budget_ok else "LOCAL_RESEARCH_BLOCKED",
                              "Research-only virtual capital and max-loss bps check"),
        Stage75ReadinessCheck("global_fo_risk_capital_gate", "EXTERNAL_MISSING",
                              "Stage69 synthetic EQUITY_DELIVERY gate cannot authorize F&O"),
        Stage75ReadinessCheck("real_fo_forward_shadow_evidence", "EXTERNAL_MISSING",
                              "No authenticated market-data, realized fills or signed trial"),
    )
    blockers = _EXTERNAL + (() if local_budget_ok else ("RESEARCH_PREMIUM_OR_STRESS_BUDGET_EXCEEDED",))
    packet = json.dumps([
        stage71.underlying, stage72.symbol, first.strike, first.option_type,
        a71, s72, r73, r74, budget.account_id,
        budget.virtual_capital_cents, budget.max_single_option_debit_bps,
        budget.max_scenario_loss_bps, debit, largest_loss, stage73.paired_count,
        [x.status for x in checks], blockers,
    ], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return Stage75FOShadowReadinessPacket(
        underlying=stage71.underlying, option_symbol=stage72.symbol,
        selected_strike=first.strike, selected_option_type=first.option_type,
        source_stage71_sha256=a71, source_stage72_sha256=s72,
        stage73_review_sha256=r73, stage74_scenarios_sha256=r74,
        account_id=budget.account_id, virtual_capital_cents=budget.virtual_capital_cents,
        long_option_entry_debit_cents=debit,
        maximum_hypothetical_scenario_loss_cents=largest_loss,
        option_debit_allocation_bps_rounded_up=entry_bps,
        maximum_scenario_loss_bps_rounded_up=loss_bps,
        research_budget_screen_passed=local_budget_ok,
        paired_oos_research_samples=stage73.paired_count,
        local_chain_structurally_consistent=True,
        checks=checks, blockers=blockers,
        research_packet_sha256=hashlib.sha256(packet.encode("utf-8")).hexdigest(),
    )
