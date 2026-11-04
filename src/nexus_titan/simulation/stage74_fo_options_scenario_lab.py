"""Stage74: expiry-aware, offline F&O long-option scenario research (NO-LIVE).

No executable quotes, fills, actual P&L, backtests or trading permissions.
Reuses the Stage72 unrounded Black-Scholes research model and Indian
indicative tariff; never guesses real order-book depth from OI/volume.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.derivatives.options_engine import OptionGreeks
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    Stage72OptionsResearchReport, Stage72OptionResearchRow, _price,
)

_IST = ZoneInfo("Asia/Kolkata")
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z", re.ASCII)
_ALLOWED = ("NIFTY", "BANKNIFTY")


class Stage74ScenarioBlocked(ValueError):
    """No scenario results emitted if any source/policy entry is invalid."""


@dataclass(frozen=True, slots=True)
class Stage74StressCase:
    name: str
    underlying_move_pct: float
    iv_shift_percentage_points: float
    minutes_elapsed: int
    spread_multiplier: float
    exit_slippage_bps: int
    liquidity_haircut_bps: int


@dataclass(frozen=True, slots=True)
class Stage74StressOutcome:
    case_name: str
    strike: float
    option_type: str
    lots: int
    quantity: int
    stressed_spot: float
    stressed_iv: float
    stressed_days_to_expiry: float
    model_price_per_unit: float
    model_value_change_rupees: float
    indicative_exit_bid_proxy: float
    hypothetical_exit_price_after_friction: float
    hypothetical_entry_debit_rupees: float
    hypothetical_exit_proceeds_rupees: float
    indicative_entry_charges_rupees: float
    indicative_exit_charges_rupees: float
    hypothetical_round_trip_net_rupees: float
    hypothetical_premium_at_risk_rupees: float
    # This is not a genuine exchange order or depth-derived fill.
    independently_verified_depth_or_fill: bool = False
    scenario_is_a_historical_backtest: bool = False


@dataclass(frozen=True, slots=True)
class Stage74ScenarioResearchReport:
    underlying: str
    symbol: str
    observation_time: datetime
    model_reference_spot: float
    source_stage72_sha256: str
    source_stage71_sha256: str
    indicative_cost_schedule: str
    outcomes: tuple[Stage74StressOutcome, ...]
    scenario_digest_sha256: str
    # Never turn synthetic scenario economics into authorization.
    real_exchange_data_authenticated: bool = False
    official_cost_tariff_authenticated: bool = False
    actual_market_depth_verified: bool = False
    live_or_historical_fills_verified: bool = False
    portfolio_margin_verified: bool = False
    calibrated_stress_probabilities_verified: bool = False
    actual_profitability_verified: bool = False
    strategy_promotion_authorized: bool = False
    paper_order_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE74_OPTIONS_SCENARIO_RESEARCH_NO_GO"


STAGE74_CASES = (
    Stage74StressCase("GAP_DOWN_IV_UP", -3.0, 10.0, 30, 2.0, 75, 1500),
    Stage74StressCase("GAP_UP_IV_DOWN", 3.0, -5.0, 30, 2.0, 75, 1500),
    Stage74StressCase("LIQUIDITY_DROUGHT", 0.0, 0.0, 10, 5.0, 250, 9500),
    Stage74StressCase("THETA_DECAY_120M", 0.0, 0.0, 120, 1.5, 25, 1000),
)


def _finite(value: object, name: str, low: float, high: float) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not low <= value <= high):
        raise Stage74ScenarioBlocked(name + " must be finite within allowed bounds")
    return float(value)


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Stage74ScenarioBlocked(name + " must have timezone")
    return value.astimezone(timezone.utc)


def _source_report(report: object, contract: object) -> None:
    if not isinstance(report, Stage72OptionsResearchReport) or not isinstance(contract, PointInTimeContractSpec):
        raise Stage74ScenarioBlocked("Typed Stage72 report and F&O contract required")
    flags = (
        "contract_master_independently_authenticated", "vendor_and_licence_independently_authenticated",
        "official_expiry_cutoff_authenticated", "tradeable_bid_ask_depth_verified",
        "model_calibration_or_accuracy_verified", "expiry_settlement_and_costs_verified",
        "strategy_promotion_authorized", "paper_order_authorized", "live_trading_enabled",
    )
    if (report.release_verdict != "STAGE72_IV_GREEKS_RESEARCH_ONLY_NO_GO"
            or any(getattr(report, flag, None) is not False for flag in flags)
            or type(report.broker_orders_transmitted) is not int
            or report.broker_orders_transmitted != 0):
        raise Stage74ScenarioBlocked("Source report cannot confer external authorization")
    if (not isinstance(report.research_output_sha256, str)
            or not _SHA.fullmatch(report.research_output_sha256)
            or not isinstance(report.source_alignment_sha256, str)
            or not _SHA.fullmatch(report.source_alignment_sha256)):
        raise Stage74ScenarioBlocked("Missing source hash lineage")
    observed = _utc(report.observation_time, "Stage72 observation")
    expiry = _utc(report.declared_expiry_cutoff, "Declared expiry")
    if (report.underlying not in _ALLOWED or report.underlying != contract.underlying
            or report.symbol != contract.symbol or contract.segment != "OPTIONS"
            or contract.exchange.upper() != "NSE"
            or not contract.source_verified or not contract.source_reference
            or contract.expiry_date is None
            or contract.expiry_date != expiry.astimezone(_IST).date()
            or not contract.effective_from <= observed.astimezone(_IST).date() <= contract.effective_to
            or not isinstance(report.rows, tuple) or not report.rows
            or len(report.rows) > 200 or observed >= expiry):
        raise Stage74ScenarioBlocked("Contract, expiry or Stage72 structural identity mismatch")


def simulate_stage74_long_option_scenarios(
    *,
    report: Stage72OptionsResearchReport,
    contract: PointInTimeContractSpec,
    reference_spot: float,
    strike: float,
    option_type: str,
    lots: int,
    scenarios: tuple[Stage74StressCase, ...] = STAGE74_CASES,
    costs: IndianCostConfig | None = None,
    min_minutes_to_expiry: int = 60,
) -> Stage74ScenarioResearchReport:
    """Calculate hypothetical long-CE/PE marks under declared stress assumptions.

    The exit bid proxy and statutory charges are *hypothetical* only. Their
    use does not establish a market quote, fill, margin check or profitability.
    Rejection of one scenario rejects the entire report.
    """
    _source_report(report, contract)
    spot = _finite(reference_spot, "Reference spot", 0.01, 1e8)
    target_strike = _finite(strike, "Strike", 0.01, 1e8)
    if (option_type not in ("CE", "PE") or type(lots) is not int
            or not 1 <= lots <= contract.max_lots_per_trade
            or lots * contract.lot_size > contract.freeze_quantity):
        raise Stage74ScenarioBlocked("Only bounded long CE/PE lot quantities supported")
    if (not isinstance(scenarios, tuple) or not 1 <= len(scenarios) <= 12
            or type(min_minutes_to_expiry) is not int
            or not 30 <= min_minutes_to_expiry <= 720):
        raise Stage74ScenarioBlocked("Invalid bounded scenario policy")
    tariff = costs if costs is not None else IndianCostConfig()
    if not isinstance(tariff, IndianCostConfig):
        raise Stage74ScenarioBlocked("Explicit indicative Indian tariff required")
    if (not isinstance(tariff.version, str) or not tariff.version.strip()
            or not isinstance(tariff.effective_date, str) or not tariff.effective_date.strip()):
        raise Stage74ScenarioBlocked("Invalid cost tariff reference")
    try:
        calculate_indian_trade_costs("BUY", 1.0, 1, "OPTIONS", tariff)
        calculate_indian_trade_costs("SELL", 1.0, 1, "OPTIONS", tariff)
    except (TypeError, ValueError, OverflowError) as exc:
        raise Stage74ScenarioBlocked("Invalid indicative statutory cost tariff inputs") from exc
    observed = _utc(report.observation_time, "Stage72 observation")
    expiry = _utc(report.declared_expiry_cutoff, "Expiry cutoff")
    local_observed = observed.astimezone(_IST)
    if not time(9, 15) <= local_observed.time() < time(15, 30):
        raise Stage74ScenarioBlocked("Outside regular Indian options research session")
    years_now = (expiry - observed).total_seconds() / (365.0 * 86400.0)
    rate = _finite(report.risk_free_rate_assumption, "Assumed rate", -0.1, 0.5)
    dividend = _finite(report.dividend_yield_assumption, "Assumed dividend yield", 0.0, 0.5)
    selected = [r for r in report.rows if r.strike == target_strike and r.option_type == option_type]
    if len(selected) != 1 or not isinstance(selected[0], Stage72OptionResearchRow):
        raise Stage74ScenarioBlocked("Exactly one eligible option row required")
    row = selected[0]
    if not isinstance(row.model_greeks_at_mid, OptionGreeks):
        raise Stage74ScenarioBlocked("Missing model Greeks baseline")
    bid = _finite(row.bid, "Input bid", 0.01, 1e8)
    ask = _finite(row.ask, "Input ask", 0.01, 1e8)
    mid = _finite(row.midpoint, "Input midpoint", 0.01, 1e8)
    vol = _finite(row.iv_mid, "Input IV", 0.01, 3.0)
    if bid > ask or abs((bid + ask) / 2.0 - mid) > 0.001:
        raise Stage74ScenarioBlocked("Inconsistent option bid/ask midpoint")
    anchor_price = _price(spot, target_strike, years_now, vol, rate, dividend, option_type)
    if abs(anchor_price - mid) > 0.2:
        raise Stage74ScenarioBlocked("Declared spot does not reproduce Stage72 IV baseline")
    quantity = contract.lot_size * lots
    entry_fees = calculate_indian_trade_costs("BUY", ask, quantity, "OPTIONS", tariff).total_charges
    outcomes: list[Stage74StressOutcome] = []
    seen: set[str] = set()
    for case in scenarios:
        if not isinstance(case, Stage74StressCase):
            raise Stage74ScenarioBlocked("Scenario type must be declared")
        if (not isinstance(case.name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", case.name)
                or case.name in seen):
            raise Stage74ScenarioBlocked("Scenario name invalid or duplicate")
        seen.add(case.name)
        move = _finite(case.underlying_move_pct, "Spot shock pct", -20.0, 20.0)
        shift = _finite(case.iv_shift_percentage_points, "IV shift percentage points", -40.0, 40.0)
        multiplier = _finite(case.spread_multiplier, "Spread multiplier", 1.0, 10.0)
        if (type(case.minutes_elapsed) is not int or not 0 <= case.minutes_elapsed <= 1440
                or type(case.exit_slippage_bps) is not int or not 0 <= case.exit_slippage_bps <= 500
                or type(case.liquidity_haircut_bps) is not int
                or not 0 <= case.liquidity_haircut_bps <= 10000):
            raise Stage74ScenarioBlocked("Invalid scenario clock or friction assumptions")
        stressed_at = observed + timedelta(minutes=case.minutes_elapsed)
        remaining = (expiry - stressed_at).total_seconds()
        if remaining <= min_minutes_to_expiry * 60:
            raise Stage74ScenarioBlocked("Too close to expiry for BSM scenario approximation")
        local_stressed = stressed_at.astimezone(_IST)
        if (local_stressed.date() != local_observed.date()
                or not time(9, 15) <= local_stressed.time() < time(15, 30)):
            raise Stage74ScenarioBlocked("Cross-session stress requires independent scenario data")
        stressed_spot = spot * (1.0 + move / 100.0)
        stressed_vol = vol + shift / 100.0
        if not (stressed_spot > 0 and 0.01 <= stressed_vol <= 3.0):
            raise Stage74ScenarioBlocked("Stressed spot or IV outside model domain")
        stressed_years = remaining / (365.0 * 86400.0)
        mark = _price(stressed_spot, target_strike, stressed_years, stressed_vol, rate, dividend, option_type)
        if not math.isfinite(mark) or mark < 0:
            raise Stage74ScenarioBlocked("Stressed theoretical mark invalid")
        # Quote width is a user-supplied stress assumption; there is NO depth.
        proxy_bid = max(0.0, mark - (ask - bid) / 2.0 * multiplier)
        sell_proxy = proxy_bid * (1.0 - case.exit_slippage_bps / 10000.0)
        sell_proxy *= 1.0 - case.liquidity_haircut_bps / 10000.0
        if sell_proxy <= 0:
            # No marketable exit is being represented: do not fabricate a fill.
            exit_fees = 0.0
        else:
            exit_fees = calculate_indian_trade_costs(
                "SELL", sell_proxy, quantity, "OPTIONS", tariff,
            ).total_charges
            # Rational research choice: do not invent a loss-making sale whose
            # fees exceed its modeled gross proceeds; no fill is asserted.
            if sell_proxy * quantity <= exit_fees:
                sell_proxy, exit_fees = 0.0, 0.0
        debit = ask * quantity + entry_fees
        exit_proceeds = sell_proxy * quantity - exit_fees
        outcomes.append(Stage74StressOutcome(
            case_name=case.name,
            strike=target_strike, option_type=option_type,
            lots=lots, quantity=quantity,
            stressed_spot=round(stressed_spot, 4),
            stressed_iv=round(stressed_vol, 6),
            stressed_days_to_expiry=round(remaining / 86400.0, 8),
            model_price_per_unit=round(mark, 6),
            model_value_change_rupees=round((mark-mid)*quantity, 2),
            indicative_exit_bid_proxy=round(proxy_bid, 6),
            hypothetical_exit_price_after_friction=round(sell_proxy, 6),
            hypothetical_entry_debit_rupees=round(debit, 2),
            hypothetical_exit_proceeds_rupees=round(exit_proceeds, 2),
            indicative_entry_charges_rupees=entry_fees,
            indicative_exit_charges_rupees=exit_fees,
            hypothetical_round_trip_net_rupees=round(exit_proceeds-debit, 2),
            hypothetical_premium_at_risk_rupees=round(debit, 2),
        ))
    digest = hashlib.sha256(json.dumps({
        "source_stage72": report.research_output_sha256.lower(),
        "source_stage71": report.source_alignment_sha256.lower(),
        "spot": spot, "strike": target_strike, "option_type": option_type,
        "lots": lots, "tariff": asdict(tariff),
        "scenario_inputs": [asdict(c) for c in scenarios],
        "outputs": [asdict(o) for o in outcomes],
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return Stage74ScenarioResearchReport(
        underlying=report.underlying, symbol=report.symbol, observation_time=observed,
        model_reference_spot=spot,
        source_stage72_sha256=report.research_output_sha256.lower(),
        source_stage71_sha256=report.source_alignment_sha256.lower(),
        indicative_cost_schedule=tariff.version,
        outcomes=tuple(outcomes), scenario_digest_sha256=digest,
    )
