"""Stage69: read-only linkage of two independent *synthetic-only* QA modules.

Rebuilds risk-screen cash/reserve fields from Stage53's current standalone
local budget ledger rather than accepting caller-supplied balances, screens a
synthetic equity BUY with Stage56, then checks Stage53's own caps.  It never
takes a hold, issues an order or fill, authenticates a caller, or prevents
legacy VirtualAccount/CryptoVirtualAccount direct Python API calls.

This preflight is NOT global Risk & Veto, a broker security boundary, a
capital service or transaction-level atomic execution. External NO-GO persists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nexus_titan.operations.brokerless_risk_veto import (
    Stage56RiskPolicy, Stage56SyntheticIntent, Stage56SyntheticQuote,
    Stage56SyntheticRiskState, inspect_stage56_synthetic_risk,
)
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53SyntheticCapitalAuthority,
)


@dataclass(frozen=True, slots=True)
class Stage69UntrustedRiskTelemetry:
    daily_realized_loss_bps: int
    current_drawdown_bps: int
    consecutive_losses: int
    kill_switch_active: bool
    risk_module_healthy: bool


@dataclass(frozen=True, slots=True)
class Stage69ResearchPreflight:
    account_id: str
    request_id: str
    source: str
    local_budget_integrity_checked: bool
    local_synthetic_risk_screen_passed: bool
    local_budget_caps_checked: bool
    local_research_preflight_passed: bool
    requested_notional_cents: int | None
    blockers: tuple[str, ...]
    observed_budget_revision: int | None
    # No authority over actual trades, holdings, separate ledgers or users.
    caller_risk_telemetry_authenticated: bool = False
    independently_authenticated_market_quote: bool = False
    global_legacy_entrypoints_fenced: bool = False
    single_atomic_authority_for_all_ledger_books: bool = False
    risk_rechecked_at_real_fill: bool = False
    authenticated_owner_approval: bool = False
    budget_hold_performed: bool = False
    order_submission_authorized: bool = False
    strategy_promotion_authorized: bool = False
    real_money_trading_enabled: bool = False
    production_ready: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "RESEARCH_ONLY_GLOBAL_RISK_NO_GO"


def inspect_stage69_synthetic_risk_budget(
    authority: Stage53SyntheticCapitalAuthority,
    intent: Stage56SyntheticIntent,
    quote: Stage56SyntheticQuote,
    telemetry: Stage69UntrustedRiskTelemetry,
    *,
    risk_policy: Stage56RiskPolicy = Stage56RiskPolicy(),
    now: datetime | None = None,
) -> Stage69ResearchPreflight:
    """Only read local balance, then screen one synthetic BUY. No mutation.

    Local budget may change between inspect and future action (TOCTOU). There
    is deliberately NO hold/commit method in this API. A real independent
    authority must verify quote, identity, account, risk and spend atomically.
    """
    if not isinstance(authority, Stage53SyntheticCapitalAuthority):
        raise TypeError("A real Stage53SyntheticCapitalAuthority instance is required")
    if not isinstance(risk_policy, Stage56RiskPolicy):
        raise TypeError("Stage56RiskPolicy required")
    issues: list[str] = []
    status = authority.inspect()
    is_clean = (
        status.local_integrity_verified
        and status.account_id == authority.account_id
        and status.initial_cents == authority.initial_cents
        and type(status.held_cents) is int
        and type(status.remaining_cents) is int
        and type(status.revision) is int
        and status.held_cents >= 0 and status.remaining_cents >= 0
        and status.held_cents + status.remaining_cents == status.initial_cents
        and not status.blockers
    )
    if not is_clean:
        issues.append("LOCAL_SYNTHETIC_BUDGET_UNVERIFIABLE")
    telemetry_valid = isinstance(telemetry, Stage69UntrustedRiskTelemetry) and (
        type(telemetry.daily_realized_loss_bps) is int
        and type(telemetry.current_drawdown_bps) is int
        and type(telemetry.consecutive_losses) is int
        and type(telemetry.kill_switch_active) is bool
        and type(telemetry.risk_module_healthy) is bool
    )
    if not telemetry_valid:
        issues.append("CALLER_RISK_TELEMETRY_MALFORMED")
    # Never import untrusted caller balances into a Stage56 account screen.
    valid_account = is_clean and telemetry_valid
    risk_pass = False
    notional = None
    local_caps = False
    if valid_account:
        account = Stage56SyntheticRiskState(
            account_id=status.account_id,
            initial_cents=status.initial_cents,
            available_cents=status.remaining_cents,
            already_reserved_cents=status.held_cents,
            daily_realized_loss_bps=telemetry.daily_realized_loss_bps,
            current_drawdown_bps=telemetry.current_drawdown_bps,
            consecutive_losses=telemetry.consecutive_losses,
            kill_switch_active=telemetry.kill_switch_active,
            risk_module_healthy=telemetry.risk_module_healthy,
        )
        screened = inspect_stage56_synthetic_risk(
            intent, quote, account, policy=risk_policy, now=now,
        )
        risk_pass = screened.local_synthetic_screen_passed
        notional = screened.synthetic_notional_cents
        issues.extend(screened.blockers)
        if type(notional) is int and notional > 0:
            # These are Stage53 caps, separate from Stage56 caps.
            if notional * 10000 > status.initial_cents * authority.policy.max_single_hold_bps:
                issues.append("STAGE53_SINGLE_HOLD_CAP_VETO")
            elif (notional + status.held_cents) * 10000 > (
                status.initial_cents * authority.policy.max_aggregate_held_bps
            ):
                issues.append("STAGE53_AGGREGATE_HOLD_CAP_VETO")
            elif notional > status.remaining_cents:
                issues.append("STAGE53_NO_FREE_SYNTHETIC_BUDGET")
            else:
                local_caps = True
        else:
            issues.append("SYNTHETIC_NOTIONAL_UNAVAILABLE")
    report = Stage69ResearchPreflight(
        account_id=status.account_id,
        request_id=intent.request_id if isinstance(intent, Stage56SyntheticIntent)
            and isinstance(intent.request_id, str) else "UNVERIFIED",
        source="STAGE69_BROKERLESS_LOCAL_SYNTHETIC_BUDGET_QA",
        local_budget_integrity_checked=is_clean,
        local_synthetic_risk_screen_passed=risk_pass,
        local_budget_caps_checked=local_caps,
        local_research_preflight_passed=(valid_account and risk_pass and local_caps
                                         and not issues),
        requested_notional_cents=notional,
        blockers=tuple(dict.fromkeys(issues)),
        observed_budget_revision=status.revision if is_clean else None,
    )
    return report
