"""Stage76: bounded portfolio-level NIFTY/BANKNIFTY long-option research fence.

Consumes *operator-supplied* Stage75 research-only readiness packets. This
does not mutate or synchronize Stage19/43/53/55 capital, risk or paper books,
and is not called by their direct order/fill entrypoints. No broker/order API.
Local pass MUST NEVER be interpreted as risk authorization or deployment.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Literal

from nexus_titan.shadow.stage75_fo_shadow_readiness import (
    Stage75FOShadowReadinessPacket, Stage75ReadinessCheck,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z", re.ASCII)
_MARKETS = ("NIFTY", "BANKNIFTY")
_GLOBAL_BLOCKERS = (
    "LEGACY_VIRTUAL_ORDER_FILL_ENTRYPOINTS_NOT_GLOBALLY_FENCED",
    "STAGE19_43_53_55_BOOKS_NOT_A_SINGLE_ATOMIC_CAPITAL_AUTHORITY",
    "INDEPENDENT_RISK_TELEMETRY_AND_KILL_SWITCH_UNAUTHENTICATED",
    "EXCHANGE_QUOTES_MARGIN_FEES_AND_LICENSE_NOT_AUTHENTICATED",
    "REAL_FEED_SHADOW_TRIAL_AND_OWNER_APPROVAL_REQUIRED",
    "MAIN_INTEGRATION_AND_PROTECTED_CI_REVIEW_REQUIRED",
)
_REQUIRED_STAGE75_BLOCKERS = (
    "GLOBAL_UNBYPASSABLE_FO_RISK_GATE_NOT_VERIFIED",
    "ATOMIC_FO_CAPITAL_RESERVATIONS_NOT_VERIFIED",
)
_REQUIRED_STAGE75_CHECKS = (
    "point_in_time_research_chain",
    "out_of_sample_model_review",
    "long_option_scenario_accounting",
    "variable_capital_stress_budget",
    "global_fo_risk_capital_gate",
    "real_fo_forward_shadow_evidence",
)


class Stage76RiskBlocked(ValueError):
    """Inconsistent caller-supplied portfolio research evidence; NO-GO."""


@dataclass(frozen=True, slots=True)
class Stage76FOResearchPolicy:
    max_single_debit_bps: int = 2500
    max_portfolio_debit_bps: int = 4500
    max_per_underlying_debit_bps: int = 3500
    max_stressed_loss_bps: int = 2500
    max_daily_loss_bps: int = 300
    max_drawdown_bps: int = 1000
    max_consecutive_losses: int = 3
    max_research_ideas: int = 8

    def __post_init__(self):
        rules = (
            ("single_debit", self.max_single_debit_bps, 1, 5000),
            ("portfolio_debit", self.max_portfolio_debit_bps, 1, 7000),
            ("per_underlying_debit", self.max_per_underlying_debit_bps, 1, 6000),
            ("stressed_loss", self.max_stressed_loss_bps, 1, 5000),
            ("daily_loss", self.max_daily_loss_bps, 1, 1500),
            ("drawdown", self.max_drawdown_bps, 1, 3000),
            ("loss_streak", self.max_consecutive_losses, 1, 20),
            ("max_ideas", self.max_research_ideas, 1, 20),
        )
        if any(type(v) is not int or not low <= v <= high for _, v, low, high in rules):
            raise Stage76RiskBlocked("Research policy requires conservative bounded integers")
        if (self.max_single_debit_bps > self.max_portfolio_debit_bps
                or self.max_per_underlying_debit_bps > self.max_portfolio_debit_bps):
            raise Stage76RiskBlocked("Risk sublimits cannot exceed portfolio budget")


@dataclass(frozen=True, slots=True)
class Stage76UntrustedRiskTelemetry:
    account_id: str
    daily_realized_loss_bps: int
    drawdown_bps: int
    consecutive_losses: int
    kill_switch_active: bool
    risk_engine_healthy: bool
    # ALL values caller-supplied; no signature, privileged data or proof.


@dataclass(frozen=True, slots=True)
class Stage76UnderlyingExposure:
    underlying: str
    idea_count: int
    hypothetical_debit_cents: int
    hypothetical_loss_cents: int
    debit_allocation_bps_rounded_up: int


@dataclass(frozen=True, slots=True)
class Stage76FOPortfolioRiskReview:
    account_id: str
    virtual_capital_cents: int
    research_idea_count: int
    total_hypothetical_debit_cents: int
    total_hypothetical_stress_loss_cents: int
    max_theoretical_premium_loss_cents: int
    total_debit_allocation_bps_rounded_up: int
    total_stress_loss_bps_rounded_up: int
    underlying_exposures: tuple[Stage76UnderlyingExposure, ...]
    local_portfolio_budget_checks_passed: bool
    local_untrusted_risk_telemetry_checks_passed: bool
    local_research_fence_passed: bool
    input_packet_sha256: tuple[str, ...]
    local_research_audit_sha256: str
    blockers: tuple[str, ...]
    # These flags never become true on the basis of local research checks.
    current_positions_and_pending_orders_reconciled: bool = False
    authoritative_capital_or_reservation_performed: bool = False
    global_mandatory_fo_risk_veto_enforced: bool = False
    independent_risk_telemetry_authenticated: bool = False
    historical_real_fo_data_verified: bool = False
    actual_fill_or_shadow_pnl_verified: bool = False
    owner_approval_authenticated: bool = False
    order_submission_authorized: bool = False
    paper_order_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE76_OFFLINE_FO_PORTFOLIO_RISK_REVIEW_NO_GO"


def _bps(amount: int, capital: int) -> int:
    return (amount * 10000 + capital - 1) // capital


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise Stage76RiskBlocked(label + " must be bounded ASCII identifier")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise Stage76RiskBlocked(label + " must have SHA-256 format")
    return value.lower()


def _amount(value: object, label: str, *, positive: bool = False) -> int:
    if (type(value) is not int or not (1 if positive else 0) <= value <= 10**14):
        raise Stage76RiskBlocked(label + " must be bounded nonnegative integer paise")
    return value


def inspect_stage76_fo_portfolio_risk(
    *,
    packets: tuple[Stage75FOShadowReadinessPacket, ...],
    policy: Stage76FOResearchPolicy,
    telemetry: Stage76UntrustedRiskTelemetry,
) -> Stage76FOPortfolioRiskReview:
    """Aggregate alternative long-option research ideas without making orders.

    Maximum sum of *individual* stressed losses is deliberately conservative,
    but is NOT a measured joint-tail VaR or independently verified worst case.
    """
    if not isinstance(policy, Stage76FOResearchPolicy) or not isinstance(telemetry, Stage76UntrustedRiskTelemetry):
        raise Stage76RiskBlocked("Typed research policy and risk telemetry required")
    if not isinstance(packets, tuple) or not packets or len(packets) > policy.max_research_ideas:
        raise Stage76RiskBlocked("Nonempty bounded research packet tuple required")
    account = _id(telemetry.account_id, "Risk telemetry account")
    limits = (telemetry.daily_realized_loss_bps, telemetry.drawdown_bps,
              telemetry.consecutive_losses)
    if (any(type(x) is not int or not 0 <= x <= 10000 for x in limits)
            or type(telemetry.kill_switch_active) is not bool
            or type(telemetry.risk_engine_healthy) is not bool):
        raise Stage76RiskBlocked("Untrusted telemetry must be correctly typed and bounded")
    cap: int | None = None
    seen_ideas: set[tuple[str, str, float]] = set()
    digests: list[str] = []
    rows: list[tuple[str, int, int]] = []
    local_stage75_pass = True
    for packet in packets:
        if not isinstance(packet, Stage75FOShadowReadinessPacket):
            raise Stage76RiskBlocked("Stage75 readiness packet type required")
        if _id(packet.account_id, "Stage75 account") != account:
            raise Stage76RiskBlocked("Cross-account funding cannot be aggregated")
        if packet.underlying not in _MARKETS or packet.selected_option_type not in ("CE", "PE"):
            raise Stage76RiskBlocked("Only NIFTY/BANKNIFTY long CE/PE research supported")
        if (not isinstance(packet.option_symbol, str) or not packet.option_symbol
                or len(packet.option_symbol) > 64
                or type(packet.selected_strike) not in (float, int)
                or not 0 < packet.selected_strike <= 10**9):
            raise Stage76RiskBlocked("Invalid contract symbol or strike")
        key = (packet.underlying, packet.selected_option_type, packet.selected_strike)
        if key in seen_ideas:
            raise Stage76RiskBlocked("Duplicate strike/side risks double-counting portfolio")
        seen_ideas.add(key)
        packet_cap = _amount(packet.virtual_capital_cents, "Stage75 virtual capital", positive=True)
        if cap is None:
            cap = packet_cap
        if packet_cap != cap:
            raise Stage76RiskBlocked("Different capital snapshots; no atomic shared ledger")
        debit = _amount(packet.long_option_entry_debit_cents, "Stage75 debit", positive=True)
        loss = _amount(packet.maximum_hypothetical_scenario_loss_cents, "Stage75 stress loss")
        if (debit > cap or loss > debit
                or packet.option_debit_allocation_bps_rounded_up != _bps(debit, cap)
                or packet.maximum_scenario_loss_bps_rounded_up != _bps(loss, cap)):
            raise Stage76RiskBlocked("Stage75 virtual capital and loss arithmetic mismatch")
        for attribute in (
            "independently_authenticated_fo_source", "independently_verified_forward_outcomes",
            "official_margin_and_fees_verified", "global_risk_veto_unbypassable",
            "atomic_capital_book_verified", "owner_approval_authenticated",
            "real_shadow_trading_started", "paper_order_authorized",
            "strategy_promotion_authorized", "live_trading_enabled",
        ):
            if getattr(packet, attribute, None) is not False:
                raise Stage76RiskBlocked("Stage75 claimed external execution/approval authority")
        if (type(packet.actual_fills_recorded) is not int or packet.actual_fills_recorded != 0
                or type(packet.broker_orders_transmitted) is not int
                or packet.broker_orders_transmitted != 0
                or packet.verdict != "STAGE75_FO_SHADOW_READINESS_RESEARCH_NO_GO"):
            raise Stage76RiskBlocked("Stage75 verdict/fill safety boundary violated")
        for field in ("source_stage71_sha256", "source_stage72_sha256",
                      "stage73_review_sha256", "stage74_scenarios_sha256"):
            _sha(getattr(packet, field), field)
        digest = _sha(packet.research_packet_sha256, "Stage75 packet digest")
        if (not isinstance(packet.checks, tuple)
                or not isinstance(packet.blockers, tuple)
                or not set(_REQUIRED_STAGE75_BLOCKERS).issubset(packet.blockers)
                or set(c.name for c in packet.checks if isinstance(c, Stage75ReadinessCheck))
                   != set(_REQUIRED_STAGE75_CHECKS)
                or len(packet.checks) != len(_REQUIRED_STAGE75_CHECKS)):
            raise Stage76RiskBlocked("Stage75 mandatory external blockers missing")
        flags = {c.name: c.status for c in packet.checks}
        if (flags["global_fo_risk_capital_gate"] != "EXTERNAL_MISSING"
                or flags["real_fo_forward_shadow_evidence"] != "EXTERNAL_MISSING"
                or flags["variable_capital_stress_budget"]
                   != ("LOCAL_RESEARCH_PASS" if packet.research_budget_screen_passed
                       else "LOCAL_RESEARCH_BLOCKED")):
            raise Stage76RiskBlocked("Stage75 risk and external gate flags inconsistent")
        if (type(packet.local_chain_structurally_consistent) is not bool
                or type(packet.research_budget_screen_passed) is not bool):
            raise Stage76RiskBlocked("Stage75 local flags not boolean")
        local_stage75_pass &= (packet.local_chain_structurally_consistent
                               and packet.research_budget_screen_passed)
        digests.append(digest)
        rows.append((packet.underlying, debit, loss))
    assert cap is not None  # nonempty source was checked; no network or I/O
    totals = {underlying: [0, 0, 0] for underlying in _MARKETS}
    for underlying, debit, loss in rows:
        value = totals[underlying]
        value[0] += 1
        value[1] += debit
        value[2] += loss
    gross_debit = sum(row[1] for row in rows)
    gross_loss = sum(row[2] for row in rows)
    exposures = tuple(Stage76UnderlyingExposure(
        underlying=u, idea_count=totals[u][0],
        hypothetical_debit_cents=totals[u][1],
        hypothetical_loss_cents=totals[u][2],
        debit_allocation_bps_rounded_up=_bps(totals[u][1], cap),
    ) for u in _MARKETS if totals[u][0] > 0)
    debit_bps, loss_bps = _bps(gross_debit, cap), _bps(gross_loss, cap)
    caps_ok = (local_stage75_pass
               and all(_bps(d, cap) <= policy.max_single_debit_bps for _, d, _ in rows)
               and debit_bps <= policy.max_portfolio_debit_bps
               and all(x.debit_allocation_bps_rounded_up <= policy.max_per_underlying_debit_bps
                       for x in exposures)
               and loss_bps <= policy.max_stressed_loss_bps
               and gross_debit <= cap)
    telemetry_ok = (
        not telemetry.kill_switch_active and telemetry.risk_engine_healthy
        and telemetry.daily_realized_loss_bps < policy.max_daily_loss_bps
        and telemetry.drawdown_bps < policy.max_drawdown_bps
        and telemetry.consecutive_losses < policy.max_consecutive_losses
    )
    dynamic_blockers = []
    if not local_stage75_pass:
        dynamic_blockers.append("STAGE75_LOCAL_RESEARCH_PREREQUISITE_FAILED")
    if not caps_ok:
        dynamic_blockers.append("AGGREGATE_FO_RESEARCH_CAPITAL_OR_STRESS_LIMIT_EXCEEDED")
    if not telemetry_ok:
        dynamic_blockers.append("UNTRUSTED_RISK_TELEMETRY_VETO_OR_HEALTH_FAILURE")
    manifest = {
        "account": account,
        "virtual_capital_cents": cap,
        "policy": asdict(policy),
        "telemetry": asdict(telemetry),
        "ideas": sorted((u, d, l, h) for (u, d, l), h in zip(rows, digests)),
        "gross_debit": gross_debit,
        "gross_loss": gross_loss,
        "blockers": _GLOBAL_BLOCKERS + tuple(dynamic_blockers),
    }
    proof = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return Stage76FOPortfolioRiskReview(
        account_id=account, virtual_capital_cents=cap,
        research_idea_count=len(packets),
        total_hypothetical_debit_cents=gross_debit,
        total_hypothetical_stress_loss_cents=gross_loss,
        max_theoretical_premium_loss_cents=gross_debit,
        total_debit_allocation_bps_rounded_up=debit_bps,
        total_stress_loss_bps_rounded_up=loss_bps,
        underlying_exposures=exposures,
        local_portfolio_budget_checks_passed=caps_ok,
        local_untrusted_risk_telemetry_checks_passed=telemetry_ok,
        local_research_fence_passed=caps_ok and telemetry_ok,
        input_packet_sha256=tuple(sorted(digests)),
        local_research_audit_sha256=proof,
        blockers=_GLOBAL_BLOCKERS + tuple(dynamic_blockers),
    )
