"""Stage72: bounded offline IV envelopes and expiry-aware option Greeks research.

Consumes one Stage71 as-of aligned *operator-supplied* option snapshot.
No vendor authentication, real order-book depth, performance claims, order
routing, strategy promotion, or executable advice. Uses Black-Scholes-Merton
as a research model, not an exact Indian index-option market-price oracle.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.stage71_fo_asof_alignment import Stage71FOLearningPreflight
from nexus_titan.derivatives.chain_integrity import inspect_verified_option_chain
from nexus_titan.derivatives.options_engine import OptionGreeks, calculate_option_greeks

_IST = ZoneInfo("Asia/Kolkata")
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z", re.ASCII)


class Stage72ResearchBlocked(ValueError):
    """Entire research snapshot is rejected rather than emitting partial Greeks."""


@dataclass(frozen=True, slots=True)
class Stage72OptionResearchRow:
    strike: float
    option_type: str
    bid: float
    ask: float
    midpoint: float
    spread_bps: float
    iv_bid: float
    iv_mid: float
    iv_ask: float
    model_greeks_at_mid: OptionGreeks


@dataclass(frozen=True, slots=True)
class Stage72OptionsResearchReport:
    underlying: str
    symbol: str
    observation_time: datetime
    declared_expiry_cutoff: datetime
    time_to_expiry_days: float
    source_option_sha256: str
    source_alignment_sha256: str
    risk_free_rate_assumption: float
    dividend_yield_assumption: float
    rows: tuple[Stage72OptionResearchRow, ...]
    research_output_sha256: str
    # Explicit limitations: never promote operator declarations to authority.
    contract_master_independently_authenticated: bool = False
    vendor_and_licence_independently_authenticated: bool = False
    official_expiry_cutoff_authenticated: bool = False
    tradeable_bid_ask_depth_verified: bool = False
    model_calibration_or_accuracy_verified: bool = False
    expiry_settlement_and_costs_verified: bool = False
    strategy_promotion_authorized: bool = False
    paper_order_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    release_verdict: str = "STAGE72_IV_GREEKS_RESEARCH_ONLY_NO_GO"


def _aware(value: object, label: str) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None):
        raise Stage72ResearchBlocked(label + " requires an aware datetime")
    return value.astimezone(timezone.utc)


def _finite(value: object, label: str, minimum: float, maximum: float) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not minimum <= value <= maximum):
        raise Stage72ResearchBlocked(label + " outside bounded finite research limits")
    return float(value)


def _price(spot: float, strike: float, years: float, sigma: float,
           rate: float, div: float, option_type: str) -> float:
    """Unrounded BSM benchmark, used only for bounded IV inversion."""
    root = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - div + sigma * sigma / 2.0) * years) / (sigma * root)
    d2 = d1 - sigma * root
    cdf = lambda z: 0.5 * math.erfc(-z / math.sqrt(2.0))
    ds = spot * math.exp(-div * years)
    dk = strike * math.exp(-rate * years)
    if option_type == "CE":
        return ds * cdf(d1) - dk * cdf(d2)
    return dk * cdf(-d2) - ds * cdf(-d1)


def _iv(target: float, spot: float, strike: float, years: float,
        rate: float, div: float, option_type: str) -> float:
    low, high = 0.01, 3.0
    price_low = _price(spot, strike, years, low, rate, div, option_type)
    price_high = _price(spot, strike, years, high, rate, div, option_type)
    if not (price_low <= target <= price_high):
        raise Stage72ResearchBlocked("IV unidentifiable inside bounded volatility bracket")
    for _ in range(64):
        mid = 0.5 * (low + high)
        if _price(spot, strike, years, mid, rate, div, option_type) >= target:
            high = mid
        else:
            low = mid
    sigma = 0.5 * (low + high)
    if abs(_price(spot, strike, years, sigma, rate, div, option_type) - target) > 0.02:
        raise Stage72ResearchBlocked("IV repricing error exceeds research tolerance")
    return sigma


def analyse_stage72_options_snapshot(
    *,
    snapshot: ResearchOptionChainSnapshot,
    contract: PointInTimeContractSpec,
    aligned: Stage71FOLearningPreflight,
    declared_expiry_cutoff: datetime,
    risk_free_rate: float,
    dividend_yield: float,
    max_spread_bps: int = 1200,
    max_quote_rows: int = 200,
    min_minutes_before_expiry: int = 60,
) -> Stage72OptionsResearchReport:
    """Treat untrusted Stage71 evidence as research only, never execution authority.

    Quote mid IV and the bid/ask IV interval are a spread uncertainty proxy,
    NOT confidence intervals or guaranteed executable volatility levels.
    """
    if (not isinstance(snapshot, ResearchOptionChainSnapshot)
            or not isinstance(contract, PointInTimeContractSpec)
            or not isinstance(aligned, Stage71FOLearningPreflight)):
        raise Stage72ResearchBlocked("Typed Stage16/Stage71 inputs required")
    if (type(max_spread_bps) is not int or not 1 <= max_spread_bps <= 1500
            or type(max_quote_rows) is not int or not 2 <= max_quote_rows <= 500
            or type(min_minutes_before_expiry) is not int
            or not 30 <= min_minutes_before_expiry <= 720):
        raise Stage72ResearchBlocked("Invalid bounded research policy")
    rate = _finite(risk_free_rate, "Risk-free rate", -0.1, 0.5)
    div = _finite(dividend_yield, "Dividend yield", 0.0, 0.5)
    observed = _aware(snapshot.observed_at, "Snapshot observation")
    cutoff = _aware(declared_expiry_cutoff, "Declared expiry cutoff")
    remaining = (cutoff - observed).total_seconds()
    if not min_minutes_before_expiry * 60 < remaining <= 366 * 86400:
        raise Stage72ResearchBlocked("Expiry too near, expired or too far for bounded Greeks")
    local_obs = observed.astimezone(_IST).date()
    local_cutoff = cutoff.astimezone(_IST)
    if (contract.exchange.upper() != "NSE"
            or contract.segment != "OPTIONS"
            or contract.underlying not in ("NIFTY", "BANKNIFTY")
            or contract.expiry_date is None
            or contract.expiry_date != local_cutoff.date()
            or not (contract.effective_from <= local_obs <= contract.effective_to)
            or not (contract.effective_from <= contract.expiry_date <= contract.effective_to)
            or not contract.source_verified or not contract.source_reference
            or not (12 <= local_cutoff.hour <= 18)):
        raise Stage72ResearchBlocked("Unverified or inconsistent declared NSE contract/expiry")
    if (aligned.underlying != contract.underlying
            or aligned.aligned_observation_count != len(aligned.observations)
            or type(aligned.aligned_observation_count) is not int
            or aligned.aligned_observation_count < 1):
        raise Stage72ResearchBlocked("Stage71 alignment identity/count mismatch")
    deny_flags = (
        "vendor_identity_independently_authenticated",
        "data_licence_independently_authenticated",
        "point_in_time_exchange_contracts_authenticated",
        "independent_calendar_verified",
        "real_market_depth_verified",
        "historically_complete_fo_universe_verified",
        "leak_free_full_training_pipeline_verified",
        "model_performance_verified",
        "approved_for_strategy_promotion",
        "paper_order_authorized",
        "live_trading_enabled",
    )
    if any(getattr(aligned, key, None) is not False for key in deny_flags):
        raise Stage72ResearchBlocked("Stage71 input falsely claims independent authority")
    if (type(aligned.broker_orders_transmitted) is not int
            or aligned.broker_orders_transmitted != 0
            or not isinstance(aligned.input_alignment_sha256, str)
            or _SHA.fullmatch(aligned.input_alignment_sha256) is None
            or not isinstance(snapshot.sha256, str)
            or _SHA.fullmatch(snapshot.sha256) is None
            or snapshot.approved_for_strategy_promotion is not False):
        raise Stage72ResearchBlocked("Unverified/invalid Stage71 or snapshot lineage")
    if not isinstance(snapshot.quotes, tuple) or not 2 <= len(snapshot.quotes) <= max_quote_rows:
        raise Stage72ResearchBlocked("Unsupported or empty option chain size")
    matches = [r for r in aligned.observations
               if r.option_snapshot_sha256.lower() == snapshot.sha256.lower()
               and r.option_observed_at == observed
               and r.option_quote_count == len(snapshot.quotes)
               and r.underlying == contract.underlying]
    if len(matches) != 1:
        raise Stage72ResearchBlocked("Snapshot is not uniquely bound to Stage71 aligned record")
    paired = matches[0]
    future_close = _aware(paired.futures_bar_closed_at, "Completed futures close")
    future_open = _aware(paired.futures_bar_opened_at, "Futures open")
    if (future_open >= future_close or future_close > observed
            or future_close.astimezone(_IST).date() != observed.astimezone(_IST).date()
            or type(paired.futures_age_seconds) is not int
            or (observed - future_close).total_seconds() != paired.futures_age_seconds
            or not isinstance(paired.futures_csv_sha256, str)
            or _SHA.fullmatch(paired.futures_csv_sha256) is None):
        raise Stage72ResearchBlocked("Incomplete, future or malformed Stage71 futures evidence")
    integrity = inspect_verified_option_chain(
        snapshot.quotes, contract, observed_at=observed,
        max_quote_age_seconds=2.0,
    )
    if not integrity.is_valid:
        raise Stage72ResearchBlocked("Option chain structurally unsafe: " + "; ".join(integrity.issues[:3]))
    days = remaining / 86400.0
    years = days / 365.0
    rows: list[Stage72OptionResearchRow] = []
    for q in snapshot.quotes:
        spot = _finite(q.underlying_spot, "Underlying spot", 0.0001, 1e9)
        strike = _finite(q.strike, "Option strike", 0.0001, 1e9)
        bid = _finite(q.bid, "Bid", 0.0001, 1e9)
        ask = _finite(q.ask, "Ask", 0.0001, 1e9)
        if q.option_type not in ("CE", "PE") or bid > ask:
            raise Stage72ResearchBlocked("Invalid option side or crossed bid/ask")
        midpoint = (bid + ask) / 2.0
        spread_bps = (ask - bid) / midpoint * 10000.0
        if spread_bps > max_spread_bps:
            raise Stage72ResearchBlocked("Wide bid/ask spread is not eligible for IV research")
        low = _iv(bid, spot, strike, years, rate, div, q.option_type)
        mid = _iv(midpoint, spot, strike, years, rate, div, q.option_type)
        high = _iv(ask, spot, strike, years, rate, div, q.option_type)
        if not (0.01 <= low <= mid <= high <= 3.0):
            raise Stage72ResearchBlocked("Nonmonotonic implied volatility envelope")
        greeks = calculate_option_greeks(
            spot, strike, days, mid, risk_free_rate=rate,
            option_type=q.option_type, dividend_yield=div,
        )
        if abs(greeks.theoretical_price - midpoint) > 0.10:
            raise Stage72ResearchBlocked("Legacy Greeks model repricing disagreement")
        rows.append(Stage72OptionResearchRow(
            strike=strike, option_type=q.option_type, bid=bid, ask=ask,
            midpoint=round(midpoint, 6), spread_bps=round(spread_bps, 4),
            iv_bid=round(low, 6), iv_mid=round(mid, 6),
            iv_ask=round(high, 6), model_greeks_at_mid=greeks,
        ))
    rows.sort(key=lambda x: (x.strike, x.option_type))
    material = [(r.strike, r.option_type, r.bid, r.ask, r.iv_bid, r.iv_mid, r.iv_ask)
                for r in rows]
    digest = hashlib.sha256(json.dumps({
        "option_sha": snapshot.sha256.lower(), "aligned_sha": aligned.input_alignment_sha256.lower(),
        "observed": observed.isoformat(), "cutoff": cutoff.isoformat(),
        "risk_free_rate": rate, "dividend_yield": div,
        "rows": material,
    }, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    return Stage72OptionsResearchReport(
        underlying=contract.underlying, symbol=contract.symbol,
        observation_time=observed, declared_expiry_cutoff=cutoff,
        time_to_expiry_days=round(days, 8),
        source_option_sha256=snapshot.sha256.lower(),
        source_alignment_sha256=aligned.input_alignment_sha256.lower(),
        risk_free_rate_assumption=rate,
        dividend_yield_assumption=div,
        rows=tuple(rows), research_output_sha256=digest,
    )
