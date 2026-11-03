"""Stage56: conservative *brokerless* risk/veto screening for synthetic BUYs.

This pure offline screening function is suitable for an isolated subprocess
experiment. Input is entirely caller supplied (untrusted), including "cash",
quote and simulated risk. Passing it authorizes NO order, fill, capital hold,
broker request, identity, or strategy promotion. Existing legacy APIs remain
bypass routes. There is no broker, network, key, or filesystem access here.

One day a properly isolated mandatory order process must own *all* actual
order credentials and recheck risk with independently attested quote/account
evidence. This is NOT that process or an enforcement security boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

_MAX_CENTS = 900_000_000_000_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9._-]{0,29}\Z", re.ASCII)


class Stage56RiskBlocked(PermissionError):
    """Invalid local QA policy. No order permissions are granted."""


@dataclass(frozen=True, slots=True)
class Stage56RiskPolicy:
    max_quote_age_seconds: int = 20
    max_spread_bps: int = 40
    max_slippage_bps: int = 15
    min_expected_edge_bps: int = 25
    max_order_units: int = 200
    max_order_notional_bps: int = 2000
    max_open_reserve_bps: int = 5000
    max_stop_risk_bps: int = 100
    max_daily_loss_bps: int = 300
    max_drawdown_bps: int = 1000
    max_consecutive_losses: int = 3

    def __post_init__(self) -> None:
        limits = (
            ("quote age", self.max_quote_age_seconds, 1, 60),
            ("spread", self.max_spread_bps, 1, 500),
            ("slippage", self.max_slippage_bps, 0, 100),
            ("edge", self.min_expected_edge_bps, 1, 500),
            ("order units", self.max_order_units, 1, 10000),
            ("notional", self.max_order_notional_bps, 1, 5000),
            ("aggregate reserve", self.max_open_reserve_bps, 1, 10000),
            ("stop risk", self.max_stop_risk_bps, 1, 500),
            ("daily loss", self.max_daily_loss_bps, 1, 1000),
            ("drawdown", self.max_drawdown_bps, 1, 3000),
            ("loss count", self.max_consecutive_losses, 1, 20),
        )
        if any(type(v) is not int or not low <= v <= high for _, v, low, high in limits):
            raise Stage56RiskBlocked("Stage56 risk policy contains invalid or overly permissive limits")
        if self.max_order_notional_bps > self.max_open_reserve_bps:
            raise Stage56RiskBlocked("Per-order cap cannot exceed overall reserved cap")


@dataclass(frozen=True, slots=True)
class Stage56SyntheticIntent:
    request_id: str
    symbol: str
    quantity: int
    limit_price_cents: int
    stop_price_cents: int
    fee_buffer_cents: int
    instrument_type: str = "EQUITY_DELIVERY"
    side: str = "BUY"


@dataclass(frozen=True, slots=True)
class Stage56SyntheticQuote:
    observed_at: datetime
    bid_cents: int
    ask_cents: int
    ask_depth_units: int
    expected_slippage_bps: int
    expected_edge_bps: int
    source_reference: str = "SYNTHETIC/LOCAL_QA"


@dataclass(frozen=True, slots=True)
class Stage56SyntheticRiskState:
    account_id: str
    initial_cents: int
    available_cents: int
    already_reserved_cents: int
    daily_realized_loss_bps: int
    current_drawdown_bps: int
    consecutive_losses: int
    kill_switch_active: bool
    risk_module_healthy: bool


@dataclass(frozen=True, slots=True)
class Stage56RiskDecision:
    schema_version: int
    account_id: str
    request_id: str
    local_synthetic_screen_passed: bool
    blockers: tuple[str, ...]
    policy_sha256: str
    input_sha256: str | None
    observed_spread_bps: float | None
    synthetic_notional_cents: int | None
    synthetic_stop_risk_cents: int | None
    local_caller_state_authenticated: bool = False
    external_quote_authenticated: bool = False
    independent_human_identity_verified: bool = False
    global_legacy_entrypoints_fenced: bool = False
    trusted_risk_service_boundary_enforced: bool = False
    order_submission_authorized: bool = False
    synthetic_fill_authorized: bool = False
    broker_orders_transmitted: int = 0
    live_trading_enabled: bool = False
    production_ready: bool = False


def _cent(value: object, *, allow_zero: bool = False) -> bool:
    return type(value) is int and (0 if allow_zero else 1) <= value <= _MAX_CENTS


def _nonnegative_bps(value: object) -> bool:
    return type(value) is int and 0 <= value <= 10000


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def inspect_stage56_synthetic_risk(
    intent: Stage56SyntheticIntent,
    quote: Stage56SyntheticQuote,
    account: Stage56SyntheticRiskState,
    *,
    policy: Stage56RiskPolicy = Stage56RiskPolicy(),
    now: datetime | None = None,
) -> Stage56RiskDecision:
    """Bounded, deterministic local QA preflight; NEVER an order approval.

    Reject bad values as vetoes, not cash authority. A reference clock may
    be injected in unit tests. Production must not trust a supplied clock.
    """
    if not isinstance(policy, Stage56RiskPolicy):
        raise Stage56RiskBlocked("Explicit Stage56 local risk policy required")
    issues: list[str] = []
    spread: float | None = None
    notional: int | None = None
    stop_risk: int | None = None
    fingerprint = None

    if not isinstance(account, Stage56SyntheticRiskState) or not (
        isinstance(account.account_id, str) and _ID.fullmatch(account.account_id)
        and _cent(account.initial_cents)
        and _cent(account.available_cents, allow_zero=True)
        and _cent(account.already_reserved_cents, allow_zero=True)
        and account.available_cents + account.already_reserved_cents <= account.initial_cents
        and _nonnegative_bps(account.daily_realized_loss_bps)
        and _nonnegative_bps(account.current_drawdown_bps)
        and type(account.consecutive_losses) is int
        and 0 <= account.consecutive_losses <= 10000
        and type(account.kill_switch_active) is bool
        and type(account.risk_module_healthy) is bool
    ):
        issues.append("UNTRUSTED_OR_INVALID_ACCOUNT_RISK_STATE")
    else:
        if account.kill_switch_active:
            issues.append("KILL_SWITCH_ACTIVE")
        if not account.risk_module_healthy:
            issues.append("RISK_MODULE_UNAVAILABLE")
        if account.daily_realized_loss_bps >= policy.max_daily_loss_bps:
            issues.append("DAILY_LOSS_VETO")
        if account.current_drawdown_bps >= policy.max_drawdown_bps:
            issues.append("DRAWDOWN_VETO")
        if account.consecutive_losses >= policy.max_consecutive_losses:
            issues.append("CONSECUTIVE_LOSS_VETO")

    valid_intent = isinstance(intent, Stage56SyntheticIntent) and (
        isinstance(intent.request_id, str) and _ID.fullmatch(intent.request_id)
        and isinstance(intent.symbol, str) and _SYMBOL.fullmatch(intent.symbol)
        and type(intent.quantity) is int and 1 <= intent.quantity <= policy.max_order_units
        and _cent(intent.limit_price_cents) and _cent(intent.stop_price_cents)
        and intent.stop_price_cents < intent.limit_price_cents
        and _cent(intent.fee_buffer_cents, allow_zero=True)
        and intent.instrument_type == "EQUITY_DELIVERY" and intent.side == "BUY"
    )
    if not valid_intent:
        issues.append("INVALID_OR_UNSUPPORTED_SYNTHETIC_BUY")
    quote_valid = isinstance(quote, Stage56SyntheticQuote) and (
        isinstance(quote.source_reference, str)
        and quote.source_reference == "SYNTHETIC/LOCAL_QA"
        and _cent(quote.bid_cents) and _cent(quote.ask_cents)
        and quote.bid_cents <= quote.ask_cents
        and type(quote.ask_depth_units) is int and 1 <= quote.ask_depth_units <= 10000000
        and _nonnegative_bps(quote.expected_slippage_bps)
        and _nonnegative_bps(quote.expected_edge_bps)
        and isinstance(quote.observed_at, datetime)
        and quote.observed_at.tzinfo is not None
        and quote.observed_at.utcoffset() is not None
    )
    if not quote_valid:
        issues.append("UNTRUSTED_OR_INVALID_SYNTHETIC_QUOTE")
    clock = datetime.now(timezone.utc) if now is None else now
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        issues.append("REFERENCE_CLOCK_UNVERIFIED")
    elif quote_valid:
        # Use the exact timedelta rather than truncating milliseconds.
        # A quote even 1 microsecond in the future must never pass.
        age = clock.astimezone(timezone.utc) - quote.observed_at.astimezone(timezone.utc)
        if age < timedelta(0) or age > timedelta(seconds=policy.max_quote_age_seconds):
            issues.append("QUOTE_STALE_OR_FUTURE_DATED")

    if quote_valid:
        # Exact integer comparison against midpoint avoids float veto bypass.
        delta = quote.ask_cents - quote.bid_cents
        midpoint2 = quote.ask_cents + quote.bid_cents
        spread = delta * 20000.0 / midpoint2
        if delta * 20000 > midpoint2 * policy.max_spread_bps:
            issues.append("SPREAD_LIMIT_VETO")
        if quote.expected_slippage_bps > policy.max_slippage_bps:
            issues.append("SLIPPAGE_LIMIT_VETO")
        if quote.expected_edge_bps < policy.min_expected_edge_bps:
            issues.append("EXPECTED_EDGE_TOO_LOW")
        if quote.expected_edge_bps < quote.expected_slippage_bps:
            issues.append("EXPECTED_EDGE_BELOW_SLIPPAGE")

    if valid_intent and quote_valid:
        if quote.ask_cents > intent.limit_price_cents:
            issues.append("ASK_EXCEEDS_LIMIT_PRICE")
        if intent.stop_price_cents >= quote.bid_cents:
            issues.append("STOP_NOT_BELOW_BID")
        if quote.ask_depth_units < intent.quantity:
            issues.append("INSUFFICIENT_SYNTHETIC_DEPTH")
        # No futures/options margin or exchange lot-size assumptions.
        notional = intent.quantity * intent.limit_price_cents + intent.fee_buffer_cents
        stop_risk = intent.quantity * (quote.ask_cents - intent.stop_price_cents) + intent.fee_buffer_cents
        if notional > _MAX_CENTS or stop_risk > _MAX_CENTS or stop_risk <= 0:
            issues.append("BOUND_EXCEEDED")
    if valid_intent and quote_valid and isinstance(account, Stage56SyntheticRiskState) and (
        _cent(account.initial_cents)
        and _cent(account.available_cents, allow_zero=True)
        and _cent(account.already_reserved_cents, allow_zero=True)
    ) and notional is not None and stop_risk is not None:
        if notional > account.available_cents:
            issues.append("INSUFFICIENT_AVAILABLE_CAPITAL")
        if notional * 10000 > account.initial_cents * policy.max_order_notional_bps:
            issues.append("SINGLE_NOTIONAL_CAP_VETO")
        if (notional + account.already_reserved_cents) * 10000 > (
            account.initial_cents * policy.max_open_reserve_bps
        ):
            issues.append("AGGREGATE_RESERVE_CAP_VETO")
        if stop_risk * 10000 > account.initial_cents * policy.max_stop_risk_bps:
            issues.append("STOP_RISK_CAP_VETO")

    if (valid_intent and quote_valid
            and isinstance(account, Stage56SyntheticRiskState)
            and isinstance(clock, datetime) and clock.tzinfo is not None
            and clock.utcoffset() is not None):
        fingerprint = _sha({
            "domain": "STAGE56_UNTRUSTED_LOCAL_QA_ONLY",
            "intent": asdict(intent),
            "quote": {**asdict(quote), "observed_at": quote.observed_at.isoformat()},
            "account": asdict(account),
        })

    return Stage56RiskDecision(
        schema_version=1,
        account_id=account.account_id if isinstance(account, Stage56SyntheticRiskState)
                   and isinstance(account.account_id, str) else "UNVERIFIED",
        request_id=intent.request_id if isinstance(intent, Stage56SyntheticIntent)
                   and isinstance(intent.request_id, str) else "UNVERIFIED",
        local_synthetic_screen_passed=not issues,
        blockers=tuple(dict.fromkeys(issues)),
        policy_sha256=_sha(asdict(policy)),
        input_sha256=fingerprint,
        observed_spread_bps=spread,
        synthetic_notional_cents=notional,
        synthetic_stop_risk_cents=stop_risk,
    )
