"""Stage64: read-only prospective shadow-trial QA and release NO-GO.

Evaluates caller-supplied daily *synthetic/unverified* trial aggregates
against a predeclared candidate policy. Reuses Stage61 research and Stage62
integration reports as negative governance evidence. No authenticated
market data, fills, trial registration, immutable signed audit, real
money, broker, strategy promotion, or order API.

A locally passing KPI is never a real shadow performance observation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.operations.integration_candidate_audit import Stage62IntegrationReview
from nexus_titan.research.stage61_evidence_scorecard import Stage61FOMarketReadinessScorecard

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,95}\Z", re.ASCII)
_MANDATORY_EXTERNAL_BLOCKERS = (
    "NO_INDEPENDENTLY_AUTHENTICATED_MARKET_DATA_OR_LICENCE",
    "NO_AUTHENTICATED_MARKET_QUOTES_BOUND_TO_ACTUAL_FILLS",
    "NO_VERIFIED_BROKER_COST_MARGIN_AND_SETTLEMENT",
    "NO_INDEPENDENTLY_ATTESTED_TRIAL_REGISTRATION_OR_TRADE_LOG",
    "NO_SIGNED_HUMAN_STRATEGY_PROMOTION",
    "NO_GLOBALLY_UNBYPASSABLE_RISK_OR_ORDER_FENCE",
    "NO_SINGLE_ATOMIC_CROSS_LEDGER_CAPITAL_AUTHORITY",
    "NO_OWNER_APPROVED_MERGED_TREE_CI_AND_SECURITY_AUDIT",
)


class Stage64TrialBlocked(ValueError):
    """Malformed or unsafe research trial input; no evidence promoted."""


def _int(value: object, label: str, low: int = 0, high: int = 10**14) -> int:
    if type(value) is not int or not low <= value <= high:
        raise Stage64TrialBlocked(label + " must be a bounded exact integer")
    return value


def _aware(value: object, label: str) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None):
        raise Stage64TrialBlocked(label + " requires timezone-aware datetime")
    return value


@dataclass(frozen=True, slots=True)
class Stage64TrialPlan:
    trial_id: str
    account_id: str
    strategy_version: str
    underlying: Literal["NIFTY", "BANKNIFTY"]
    registered_at: datetime
    start_date: date
    end_date: date
    starting_capital_cents: int
    minimum_sessions: int = 20
    minimum_closed_trades: int = 30
    minimum_execution_observations_per_trade: int = 2
    maximum_drawdown_bps: int = 1000
    minimum_gross_profit_factor: Decimal = Decimal("1.20")
    minimum_net_expectancy_cents: Decimal = Decimal("1")
    # Operator controls are NOT signed or time-attested by this module.
    independently_timestamped_registration: bool = False
    authenticated_owner_approval: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        for label in ("trial_id", "account_id", "strategy_version"):
            if not isinstance(getattr(self, label), str) or not _ID.fullmatch(getattr(self, label)):
                raise Stage64TrialBlocked("Invalid " + label)
        if self.underlying not in ("NIFTY", "BANKNIFTY"):
            raise Stage64TrialBlocked("Only one stated Indian futures underlying per trial")
        _aware(self.registered_at, "registered_at")
        if (not isinstance(self.start_date, date) or isinstance(self.start_date, datetime)
                or not isinstance(self.end_date, date) or isinstance(self.end_date, datetime)
                or self.end_date < self.start_date
                or (self.end_date - self.start_date).days > 365):
            raise Stage64TrialBlocked("Invalid bounded single-year trial dates")
        for name, lo, hi in (
            ("starting_capital_cents", 1, 10**14),
            ("minimum_sessions", 2, 366),
            ("minimum_closed_trades", 1, 100000),
            ("minimum_execution_observations_per_trade", 1, 100),
            ("maximum_drawdown_bps", 1, 10000),
        ):
            _int(getattr(self, name), name, lo, hi)
        for name in ("minimum_gross_profit_factor", "minimum_net_expectancy_cents"):
            value = getattr(self, name)
            if (not isinstance(value, Decimal) or not value.is_finite()
                    or value <= 0 or value > Decimal("1000000")):
                raise Stage64TrialBlocked("Invalid explicit Decimal " + name)
        if any(getattr(self, key) is not False for key in (
            "independently_timestamped_registration",
            "authenticated_owner_approval", "live_trading_enabled",
        )):
            raise Stage64TrialBlocked("Operator plan cannot claim external approval or live authority")


@dataclass(frozen=True, slots=True)
class Stage64DailyClaim:
    session_date: date
    observed_at: datetime
    account_id: str
    underlying: Literal["NIFTY", "BANKNIFTY"]
    source_class: Literal["FABRICATED_QA", "OPERATOR_DECLARED_PAPER"]
    opening_cash_cents: int
    closing_cash_cents: int
    gross_winning_cents: int
    gross_losing_cents: int
    fees_cents: int
    slippage_cents: int
    closed_trades: int
    winning_trades: int
    losing_trades: int
    flat_trades: int
    execution_observations: int
    missing_market_observations: int
    risk_limit_breaches: int
    unresolved_orders: int
    unvalued_open_positions: int
    claimed_max_intraday_drawdown_bps: int
    data_quality_checked: bool
    paper_orders_reconciled: bool
    evidence_reference: str
    independently_authenticated_data: bool = False
    independently_authenticated_fills: bool = False
    real_money_order_sent: bool = False


@dataclass(frozen=True, slots=True)
class Stage64TrialCheck:
    name: str
    locally_met: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class Stage64ShadowTrialGovernanceReport:
    schema_version: int
    trial_id: str
    account_id: str
    underlying: str
    declared_start: date
    declared_end: date
    supplied_sessions: int
    expected_trading_sessions: int
    missing_session_dates: tuple[date, ...]
    declared_closed_trades: int
    declared_execution_observations: int
    gross_winning_cents: int
    gross_losing_cents: int
    fees_cents: int
    slippage_cents: int
    claimed_net_pnl_cents: int
    claimed_gross_profit_factor: Decimal | None
    claimed_net_expectancy_cents: Decimal | None
    observed_closing_day_drawdown_bps: int
    claimed_max_intraday_drawdown_bps: int
    checks: tuple[Stage64TrialCheck, ...]
    local_trial_criteria_met: bool
    local_trial_sha256: str
    stage61_local_structural_check_observed: bool
    stage62_local_static_check_observed: bool
    mandatory_external_blockers: tuple[str, ...] = _MANDATORY_EXTERNAL_BLOCKERS
    data_source_independently_authenticated: bool = False
    real_fill_or_fee_calibration_verified: bool = False
    genuine_net_pnl_verified: bool = False
    prospectively_signed_trial_plan_verified: bool = False
    audited_full_portfolio_pnl_verified: bool = False
    independently_verified_human_approval: bool = False
    one_authoritative_capital_authority_verified: bool = False
    global_risk_veto_enforced: bool = False
    merge_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False
    broker_orders_transmitted: int = 0
    release_decision: str = "BLOCKED_INDEPENDENT_EXTERNAL_EVIDENCE_REQUIRED"


def inspect_stage64_shadow_trial(
    plan: Stage64TrialPlan,
    days: tuple[Stage64DailyClaim, ...],
    *,
    calendar: MarketCalendar,
    as_of: datetime,
    fo_evidence: Stage61FOMarketReadinessScorecard,
    integration: Stage62IntegrationReview,
) -> Stage64ShadowTrialGovernanceReport:
    """Evaluate synthetic/operator-claimed trial metrics; ALWAYS block promotion.

    No writes/network/order/capital calls. Dates, funding, risk, costs and
    source claims are checked structurally, NOT cryptographically verified.
    """
    if not isinstance(plan, Stage64TrialPlan):
        raise Stage64TrialBlocked("Explicit typed frozen trial plan required")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise Stage64TrialBlocked("Explicit India market calendar required")
    if not isinstance(fo_evidence, Stage61FOMarketReadinessScorecard):
        raise Stage64TrialBlocked("Stage61 research scorecard required")
    if not isinstance(integration, Stage62IntegrationReview):
        raise Stage64TrialBlocked("Stage62 integration audit required")
    _aware(as_of, "as_of")
    if (not isinstance(days, tuple) or not 1 <= len(days) <= 366
            or any(not isinstance(x, Stage64DailyClaim) for x in days)):
        raise Stage64TrialBlocked("Bounded exact tuple of daily trial claims required")
    if plan.end_date > as_of.astimezone(calendar.zone).date():
        raise Stage64TrialBlocked("Cannot complete a planned trial in the future")
    if (fo_evidence.underlying != plan.underlying
            or fo_evidence.broker_orders_transmitted != 0
            or fo_evidence.strategy_promotion_authorized is not False
            or fo_evidence.production_ready is not False
            or fo_evidence.genuine_futures_options_backtest_verified is not False
            or integration.merge_authorized is not False
            or integration.production_ready is not False
            or integration.real_money_trading_enabled is not False
            or integration.broker_orders_transmitted != 0):
        raise Stage64TrialBlocked("Cross-stage input mismatch or claimed forbidden external authority")

    expected: list[date] = []
    current = plan.start_date
    while current <= plan.end_date:
        if calendar.is_trading_day(current):
            expected.append(current)
        current += timedelta(days=1)
    if not expected or len(expected) > 366:
        raise Stage64TrialBlocked("Trial has no bounded configured trading sessions")
    earliest = expected[0]
    first_session = calendar.sessions_for_date(earliest)[0]
    first_open = datetime.combine(earliest, first_session.opens, calendar.zone)
    if plan.registered_at >= first_open:
        raise Stage64TrialBlocked("Trial plan must be declared before first configured open")
    if plan.starting_capital_cents < 1:
        raise Stage64TrialBlocked("Starting trial capital must be positive")
    totals = dict(wins=0, losses=0, fees=0, slip=0, trades=0, observations=0)
    prior_day: date | None = None
    prior_cash = plan.starting_capital_cents
    peak = prior_cash
    max_close_dd = 0
    max_claimed_intraday_dd = 0
    quality_ok = True
    risk_ok = True
    fills_ok = True
    review_balances_ok = True
    supplied_dates: set[date] = set()
    for row in days:
        if (not isinstance(row.session_date, date) or isinstance(row.session_date, datetime)
                or not plan.start_date <= row.session_date <= plan.end_date
                or not calendar.is_trading_day(row.session_date)
                or row.session_date in supplied_dates
                or (prior_day is not None and row.session_date <= prior_day)):
            raise Stage64TrialBlocked("Trial sessions must be distinct, ordered, on configured market days")
        timestamp = _aware(row.observed_at, "daily observed_at")
        if (timestamp > as_of or timestamp.astimezone(calendar.zone).date() != row.session_date):
            raise Stage64TrialBlocked("Daily record is future-dated or not on claimed India session date")
        sessions = calendar.sessions_for_date(row.session_date)
        closed = datetime.combine(row.session_date, sessions[-1].closes, calendar.zone)
        if timestamp < closed:
            raise Stage64TrialBlocked("Day-close observation recorded before configured market close")
        if (row.account_id != plan.account_id or row.underlying != plan.underlying
                or row.source_class not in ("FABRICATED_QA", "OPERATOR_DECLARED_PAPER")
                or not isinstance(row.evidence_reference, str)
                or not 1 <= len(row.evidence_reference.strip()) <= 256
                or row.independently_authenticated_data is not False
                or row.independently_authenticated_fills is not False
                or row.real_money_order_sent is not False):
            raise Stage64TrialBlocked("Source/account mismatch or prohibited authenticity/trading claim")
        for name, maximum in (
            ("opening_cash_cents", 10**14), ("closing_cash_cents", 10**14),
            ("gross_winning_cents", 10**14), ("gross_losing_cents", 10**14),
            ("fees_cents", 10**14), ("slippage_cents", 10**14),
            ("closed_trades", 100000), ("winning_trades", 100000),
            ("losing_trades", 100000), ("flat_trades", 100000),
            ("execution_observations", 1000000),
            ("missing_market_observations", 100000),
            ("risk_limit_breaches", 100000),
            ("unresolved_orders", 100000), ("unvalued_open_positions", 100000),
            ("claimed_max_intraday_drawdown_bps", 10000),
        ):
            _int(getattr(row, name), name, high=maximum)
        if row.closed_trades != row.winning_trades + row.losing_trades + row.flat_trades:
            raise Stage64TrialBlocked("Closed trade counts do not conserve")
        if (row.winning_trades == 0) != (row.gross_winning_cents == 0):
            raise Stage64TrialBlocked("Gross winning amount/count mismatch")
        if (row.losing_trades == 0) != (row.gross_losing_cents == 0):
            raise Stage64TrialBlocked("Gross losing amount/count mismatch")
        pnl = (row.gross_winning_cents - row.gross_losing_cents
               - row.fees_cents - row.slippage_cents)
        if row.opening_cash_cents != prior_cash or row.closing_cash_cents != prior_cash + pnl:
            review_balances_ok = False
        if row.data_quality_checked is not True or row.missing_market_observations:
            quality_ok = False
        if row.risk_limit_breaches or row.claimed_max_intraday_drawdown_bps > plan.maximum_drawdown_bps:
            risk_ok = False
        if (row.paper_orders_reconciled is not True or row.unresolved_orders
                or row.unvalued_open_positions):
            fills_ok = False
        totals["wins"] += row.gross_winning_cents
        totals["losses"] += row.gross_losing_cents
        totals["fees"] += row.fees_cents
        totals["slip"] += row.slippage_cents
        totals["trades"] += row.closed_trades
        totals["observations"] += row.execution_observations
        peak = max(peak, row.closing_cash_cents)
        max_close_dd = max(max_close_dd,
            (10000 * (peak - row.closing_cash_cents) + peak - 1) // peak)
        max_claimed_intraday_dd = max(
            max_claimed_intraday_dd, row.claimed_max_intraday_drawdown_bps)
        prior_cash = row.closing_cash_cents
        prior_day = row.session_date
        supplied_dates.add(row.session_date)

    missing = tuple(x for x in expected if x not in supplied_dates)
    net = totals["wins"] - totals["losses"] - totals["fees"] - totals["slip"]
    gross_pf = (Decimal(totals["wins"]) / Decimal(totals["losses"])
                if totals["losses"] > 0 else None)
    expectancy = (Decimal(net) / Decimal(totals["trades"])
                  if totals["trades"] > 0 else None)
    checks: list[Stage64TrialCheck] = []
    def add(name: str, valid: bool, explanation: str) -> None:
        checks.append(Stage64TrialCheck(name, bool(valid), explanation))
    add("registered_before_first_session", True,
        "Plan date was supplied earlier; independent trusted registration proof ABSENT")
    add("no_selectively_omitted_trading_days", not missing,
        "Compared against operator-supplied (NOT official) India calendar")
    add("minimum_session_sample", len(days) >= plan.minimum_sessions,
        "Only operator-supplied session counts, no real-market provenance")
    add("minimum_closed_trade_sample", totals["trades"] >= plan.minimum_closed_trades,
        "Only operator-claimed closed trade aggregates, no independently matched fills")
    add("cash_continuity_and_cost_conservation", review_balances_ok,
        "Each cash close must equal opening + claimed gross P&L - fees - slippage")
    add("calendar_session_data_quality", quality_ok,
        "Data quality flags are operator assertions, not vendor attestations")
    add("all_orders_reconciled_flat", fills_ok,
        "Claims no unresolved orders or unvalued positions; no broker reconciliation proof")
    add("no_risk_policy_breach", risk_ok,
        "Local declared risk counts only, no mandatory independent execution veto")
    add("execution_observation_coverage",
        totals["observations"] >= plan.minimum_execution_observations_per_trade
        * totals["trades"], "Operator-declared observations do not prove actual quote/fill linkage")
    add("gross_profit_factor_threshold",
        gross_pf is not None and gross_pf >= plan.minimum_gross_profit_factor,
        "Gross trial-claim PF excludes costs; undefined when no gross loss observations")
    add("net_expectancy_and_total_net_threshold",
        expectancy is not None and expectancy >= plan.minimum_net_expectancy_cents
        and net > 0, "Illustrative after-declared-cost per-trade expectancy only")
    add("peak_to_close_drawdown_threshold",
        max(max_close_dd, max_claimed_intraday_dd) <= plan.maximum_drawdown_bps,
        "Day-close drawdown computed; intraday drawdown remains self-declared")
    add("stage61_local_futures_evidence_review",
        fo_evidence.local_inputs_structurally_consistent,
        "Stage61 structural review does NOT authenticate market data or trading profits")
    add("stage62_local_integration_review",
        integration.local_static_review_passed,
        "Stage62 AST/CI source review does NOT prove merged-tree compatibility")
    local_met = all(x.locally_met for x in checks)
    # Hash is for deterministic fixture/comparison ONLY, not an authenticated
    # prospective trial record. Caller can rewrite all data and recompute it.
    snapshot = json.dumps({
        "plan": asdict(plan),
        "days": [asdict(x) for x in days],
        "stage61_local_fingerprint": fo_evidence.local_evidence_sha256,
        "stage62_snapshot_fingerprint": integration.frozen_pr_snapshot_sha256,
    }, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
    digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    return Stage64ShadowTrialGovernanceReport(
        schema_version=1, trial_id=plan.trial_id, account_id=plan.account_id,
        underlying=plan.underlying, declared_start=plan.start_date,
        declared_end=plan.end_date, supplied_sessions=len(days),
        expected_trading_sessions=len(expected), missing_session_dates=missing,
        declared_closed_trades=totals["trades"],
        declared_execution_observations=totals["observations"],
        gross_winning_cents=totals["wins"], gross_losing_cents=totals["losses"],
        fees_cents=totals["fees"], slippage_cents=totals["slip"],
        claimed_net_pnl_cents=net, claimed_gross_profit_factor=gross_pf,
        claimed_net_expectancy_cents=expectancy,
        observed_closing_day_drawdown_bps=max_close_dd,
        claimed_max_intraday_drawdown_bps=max_claimed_intraday_dd,
        checks=tuple(checks), local_trial_criteria_met=local_met,
        local_trial_sha256=digest,
        stage61_local_structural_check_observed=fo_evidence.local_inputs_structurally_consistent,
        stage62_local_static_check_observed=integration.local_static_review_passed,
    )
