"""Stage105: isolated read-only synthetic option fill/impact research.

Prices and displayed volumes come only from Stage102 synthetic fixtures. Fixed
integer paise calculations use conservative rounding; fees are hypothetical,
not an NSE/broker charge schedule. No order objects, exchange routes, or writes.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from .stage101_historical_bar_preflight import Stage101DataWindow
from .stage102_option_chain_preflight import (
    Stage102ChainReview, Stage102SyntheticQuote, review_stage102_synthetic_chain, Stage102Blocked,
)
from .stage104_historical_catalog_review import Stage104Catalog

class Stage105Blocked(ValueError):
    pass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)

@dataclass(frozen=True, slots=True)
class Stage105PaperIntent:
    request_id: str
    contract_id: str
    side: str
    requested_quantity: int
    max_volume_participation_bps: int
    adverse_slippage_bps: int
    estimated_fee_bps: int
    estimated_fixed_fee_paise_per_lot: int = 0
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    human_authorization_verified: bool = False
    live_trading_enabled: bool = False

@dataclass(frozen=True, slots=True)
class Stage105ExecutionPreview:
    request_id: str
    contract_id: str
    underlying: str
    currency: str
    side: str
    window_sha256: str
    chain_sha256: str
    catalog_sha256: str
    source_first_asof_ist: str
    source_last_asof_ist: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    hypothetical_price_paise: int | None
    hypothetical_gross_turnover_paise: int
    hypothetical_fee_paise: int
    hypothetical_spread_impact_paise: int
    hypothetical_cash_delta_paise: int
    scenario_sha256: str
    statutory_charges_verified: bool = False
    execution_liquidity_verified: bool = False
    actual_fill_verified: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO"


def preview_stage105_execution(
    catalog: Stage104Catalog,
    window: Stage101DataWindow,
    chain: Stage102ChainReview,
    quotes: list[Stage102SyntheticQuote] | tuple[Stage102SyntheticQuote, ...],
    intent: Stage105PaperIntent,
) -> Stage105ExecutionPreview:
    if (type(catalog) is not Stage104Catalog or type(window) is not Stage101DataWindow
            or type(chain) is not Stage102ChainReview or type(intent) is not Stage105PaperIntent):
        raise Stage105Blocked("Exact immutable upstream reports and intent required")
    if (catalog.symbol != window.symbol or catalog.currency != "INR"
        or catalog.independent_data_provider_verified is not False
        or catalog.complete_trading_calendar_verified is not False
        or catalog.historical_15y_coverage_verified is not False
        or catalog.strategy_signal_authorized is not False or catalog.live_trading_enabled is not False
        or catalog.verdict != "SYNTHETIC_CATALOG_STRUCTURE_ONLY_NO_GO"
        or window.content_sha256 not in catalog.source_window_hashes
        or not catalog.first_date <= window.trading_date <= catalog.last_date
        or chain.underlying != window.symbol
        or chain.source_window_sha256 != window.content_sha256
        or chain.structural_chain_valid is not True
        or chain.official_option_chain_verified is not False
        or chain.official_expiry_calendar_verified is not False
        or chain.executable_liquidity_verified is not False
        or chain.broker_order_authorized is not False or chain.live_trading_enabled is not False
        or chain.verdict != "SYNTHETIC_OPTION_CHAIN_STRUCTURE_ONLY_NO_GO"):
        raise Stage105Blocked("No approved synthetic lineage and no-live boundary")
    if type(quotes) not in (list, tuple):
        raise Stage105Blocked("Bounded explicit synthetic chain quotes required")
    try:
        replay = review_stage102_synthetic_chain(window, quotes, max_quote_age_seconds=60)
    except Stage102Blocked as exc:
        raise Stage105Blocked("Source chain quote replay failed") from exc
    if replay != chain:
        raise Stage105Blocked("Chain data changed since Stage102 preflight")
    if (type(intent.request_id) is not str or not _ID.fullmatch(intent.request_id)
        or type(intent.contract_id) is not str or intent.side not in ("BUY", "SELL")
        or intent.source != "LOCAL_SYNTHETIC_TEST_ONLY"
        or intent.human_authorization_verified is not False or intent.live_trading_enabled is not False):
        raise Stage105Blocked("Unsupported intent ID, side or authorization")
    for name, n, low, high in (
        ("requested_quantity", intent.requested_quantity, 1, 100_000),
        ("participation", intent.max_volume_participation_bps, 1, 10_000),
        ("slippage", intent.adverse_slippage_bps, 0, 1_000),
        ("estimated_fee_bps", intent.estimated_fee_bps, 0, 1_000),
        ("estimated_fixed_fee", intent.estimated_fixed_fee_paise_per_lot, 0, 1_000_000),
    ):
        if type(n) is not int or not low <= n <= high:
            raise Stage105Blocked(f"Invalid bounded {name}")
    matched = [q for q in quotes if q.contract_id == intent.contract_id]
    if len(matched) != 1:
        raise Stage105Blocked("Exactly one matching synthetic contract required")
    q = matched[0]
    if intent.requested_quantity % q.lot_size:
        raise Stage105Blocked("Requested quantity must be lot aligned")
    max_by_volume = q.volume * intent.max_volume_participation_bps // 10_000
    filled = min(intent.requested_quantity, (max_by_volume // q.lot_size) * q.lot_size)
    unfilled = intent.requested_quantity - filled
    price: int | None = None
    fee = turnover = spread_cost = delta = 0
    if filled:
        reference = q.ask_paise if intent.side == "BUY" else q.bid_paise
        if reference <= 0:
            raise Stage105Blocked("Zero executable-side synthetic quote")
        slippage = (reference * intent.adverse_slippage_bps + 9999) // 10_000
        price = reference + slippage if intent.side == "BUY" else reference - slippage
        if price <= 0 or price > 10**12:
            raise Stage105Blocked("Slippage price outside safe fixed-point range")
        turnover = price * filled
        if turnover > 10**12:
            raise Stage105Blocked("Synthetic order turnover exceeds safe bound")
        fee = ((turnover * intent.estimated_fee_bps + 9999) // 10_000
               + (filled // q.lot_size) * intent.estimated_fixed_fee_paise_per_lot)
        if fee > 10**12:
            raise Stage105Blocked("Synthetic modeled fees outside safe bound")
        # Conservative half-spread + execution-impact round-up.
        twice_impact = (2 * price - q.bid_paise - q.ask_paise) if intent.side == "BUY" else (q.bid_paise + q.ask_paise - 2 * price)
        if twice_impact < 0:
            raise Stage105Blocked("Unexpected favorable impact violates adverse-slip model")
        spread_cost = (twice_impact * filled + 1) // 2
        delta = -turnover-fee if intent.side == "BUY" else turnover-fee
    payload = ["STAGE105_SYNTHETIC_EXECUTION_V1", catalog.catalog_sha256, chain.chain_sha256,
               intent.request_id, intent.contract_id, intent.side, intent.requested_quantity,
               filled, unfilled, price, fee, spread_cost, delta]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage105ExecutionPreview(intent.request_id, intent.contract_id, window.symbol, "INR", intent.side,
        window.content_sha256, chain.chain_sha256, catalog.catalog_sha256,
        window.first_asof_ist, window.last_asof_ist, intent.requested_quantity,
        filled, unfilled, price, turnover, fee, spread_cost, delta, digest)
