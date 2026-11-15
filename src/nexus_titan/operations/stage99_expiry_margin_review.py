"""Stage 99: synthetic-only read-only expiry and margin eligibility preflight.

Additive to the existing derivative settlement and indicative SPAN/ELM helpers.
NO LIVE, no broker calls, no official NSE evidence assertions, no ledger mutation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
import re
from typing import Literal

from nexus_titan.derivatives.chain_and_settlement import (
    estimate_span_elm_margin,
    settle_option_at_expiry,
)


MAX_SYNTHETIC_NOTIONAL_INR = 1_000_000_000.0
MAX_BATCH_CASES = 50


class Stage99Blocked(ValueError):
    """Fail-closed eligibility or provenance validation failure."""


@dataclass(frozen=True, slots=True)
class Stage99SyntheticCase:
    contract_id: str
    underlying: Literal["NIFTY", "BANKNIFTY"]
    instrument_type: Literal["OPTIONS_LONG", "OPTIONS_SHORT", "FUTURES"]
    expiry_date: str
    settlement_timestamp: str
    quote_source: str
    quantity: int
    lot_size: int
    settlement_spot: float
    entry_price: float
    position_side: Literal["LONG", "SHORT"]
    option_type: Literal["CE", "PE"] | None = None
    strike: float | None = None
    source_currency: str = "INR"
    is_index_derivative: bool = True
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage99SyntheticReview:
    contract_id: str
    market: str
    currency: str
    instrument_type: str
    lots: int
    settlement_mode: str
    is_exercised: bool | None
    synthetic_gross_pnl: float | None
    synthetic_net_pnl: float | None
    indicative_margin_blocked: float
    official_margin_verified: bool = False
    exchange_settlement_verified: bool = False
    actual_broker_reconciled: bool = False
    can_promote_or_execute: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_PREVIEW_ONLY_NO_GO"
    evidence_note: str = (
        "Synthetic fixture only. Exchange settlement prices, actual margins, "
        "broker charges, and security permissions are unverified."
    )


@dataclass(frozen=True, slots=True)
class Stage99BatchReview:
    """Immutable non-trading results for at most 50 distinct synthetic contracts."""

    cases: tuple[Stage99SyntheticReview, ...]
    count: int
    market: str = "INDIAN_FO"
    currency: str = "INR"
    authentic_margin_verified: bool = False
    actual_settlement_verified: bool = False
    combined_live_execution_authorized: bool = False
    combined_realized_pnl: None = None
    verdict: str = "SYNTHETIC_BATCH_PREVIEW_ONLY_NO_GO"


def review_synthetic_batch(cases: tuple[Stage99SyntheticCase, ...] | list[Stage99SyntheticCase]) -> Stage99BatchReview:
    """One row per synthetic contract; never generate an authoritative portfolio sum.

    Explicit bounded collections only, to avoid consuming unbounded generators or
    running arbitrary callbacks during a supposedly read-only preflight.
    """
    if type(cases) not in (tuple, list) or not 1 <= len(cases) <= MAX_BATCH_CASES:
        raise Stage99Blocked("Batch must contain 1 to 50 explicitly supplied cases")
    if any(type(case) is not Stage99SyntheticCase for case in cases):
        raise Stage99Blocked("All batch cases must be Stage99SyntheticCase instances")
    seen: set[str] = set()
    output: list[Stage99SyntheticReview] = []
    for case in cases:
        if type(case.contract_id) is not str:
            raise Stage99Blocked("Batch contract identifier must be a string")
        if case.contract_id in seen:
            raise Stage99Blocked("Duplicate synthetic contract ID in batch")
        # The individual reviewer performs all other provenance/size/mode checks.
        item = review_synthetic_expiry_margin(case)
        seen.add(item.contract_id)
        output.append(item)
    return Stage99BatchReview(cases=tuple(output), count=len(output))


def _price(name: str, value: float, *, zero_ok: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise Stage99Blocked(f"{name} must be a finite numeric value")
    outside_range = (value < 0) if zero_ok else (value <= 0)
    if outside_range:
        raise Stage99Blocked(f"{name} out of range")


def review_synthetic_expiry_margin(case: Stage99SyntheticCase) -> Stage99SyntheticReview:
    """Check one synthetic contract and call existing indicative helpers.

    Caller input cannot turn the output into verified exchange evidence. There are
    no writes or exposure-/permission-mutating operations in this module.
    """
    if type(case) is not Stage99SyntheticCase:
        raise Stage99Blocked("Expected an exact Stage99SyntheticCase")
    if case.live_trading_enabled is not False or case.source_currency != "INR":
        raise Stage99Blocked("Live and non-INR requests are forbidden")
    if case.quote_source != "SYNTHETIC_TEST_FIXTURE":
        raise Stage99Blocked("Official/vendor price provenance is not established")
    if case.underlying not in ("NIFTY", "BANKNIFTY") or case.is_index_derivative is not True:
        raise Stage99Blocked("Only synthetic cash-settled index derivatives supported")
    if not isinstance(case.contract_id, str) or len(case.contract_id) > 120:
        raise Stage99Blocked("Invalid synthetic contract identifier")
    contract = re.fullmatch(
        r"(NIFTY|BANKNIFTY)-(\d{4}-\d{2}-\d{2})-(CE|PE|FUT)(?:-(\d+(?:\.\d+)?))?",
        case.contract_id,
    )
    if not contract or contract.group(1) != case.underlying or contract.group(2) != case.expiry_date:
        raise Stage99Blocked("Synthetic contract underlying/expiry mismatch")
    if case.instrument_type not in ("OPTIONS_LONG", "OPTIONS_SHORT", "FUTURES"):
        raise Stage99Blocked("Unsupported derivative instrument")
    if case.position_side not in ("LONG", "SHORT"):
        raise Stage99Blocked("Invalid position side")
    if isinstance(case.quantity, bool) or not isinstance(case.quantity, int) or not 1 <= case.quantity <= 1_000_000:
        raise Stage99Blocked("Invalid total contract quantity")
    if isinstance(case.lot_size, bool) or not isinstance(case.lot_size, int) or not 1 <= case.lot_size <= 10000:
        raise Stage99Blocked("Invalid contract lot size")
    if case.quantity % case.lot_size != 0:
        raise Stage99Blocked("Quantity must be a whole number of declared lots")
    _price("settlement_spot", case.settlement_spot)
    _price("entry_price", case.entry_price)
    if max(case.settlement_spot, case.entry_price) > 1e8:
        raise Stage99Blocked("Synthetic price exceeds permitted preflight bounds")
    if max(case.settlement_spot, case.entry_price) * case.quantity > MAX_SYNTHETIC_NOTIONAL_INR:
        raise Stage99Blocked("Synthetic notional exceeds bounded numerical safety limit")
    try:
        expiry = date.fromisoformat(case.expiry_date)
        tick = datetime.fromisoformat(case.settlement_timestamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise Stage99Blocked("Expiry and settlement timestamp must be valid ISO dates") from exc
    if tick.tzinfo is None or tick.utcoffset() != timedelta(hours=5, minutes=30):
        raise Stage99Blocked("Settlement timestamp must be explicit IST (+05:30)")
    if tick.date() != expiry or tick.time().replace(tzinfo=None) < time(15, 30):
        raise Stage99Blocked("Synthetic settlement must be after market close on expiry")

    if case.instrument_type == "FUTURES":
        if contract.group(3) != "FUT" or contract.group(4) is not None:
            raise Stage99Blocked("Futures synthetic contract identifier mismatched")
        if case.option_type is not None or case.strike is not None:
            raise Stage99Blocked("Futures must not include option strike/type")
        # A futures expiry cash P&L depends on positions and official clearing values.
        # An indicative preflight is fine; do not invent a fee-adjusted final P&L.
        margin = estimate_span_elm_margin(
            underlying_spot=case.settlement_spot, quantity=case.quantity,
            instrument_type="FUTURES",
        )
        gross = (case.settlement_spot - case.entry_price) * case.quantity
        if case.position_side == "SHORT":
            gross = -gross
        return Stage99SyntheticReview(
            contract_id=case.contract_id, market="INDIAN_FO", currency="INR",
            instrument_type=case.instrument_type, lots=case.quantity // case.lot_size,
            settlement_mode="SYNTHETIC_CASH_INDEX_PREVIEW",
            is_exercised=None, synthetic_gross_pnl=round(gross, 2),
            synthetic_net_pnl=None,
            indicative_margin_blocked=margin.total_margin_blocked,
            evidence_note="Futures margin is indicative only. Net P&L and actual clearing/fees unverified.",
        )
    if case.option_type not in ("CE", "PE"):
        raise Stage99Blocked("Options require CE/PE")
    if case.strike is None:
        raise Stage99Blocked("Option strike required")
    _price("strike", case.strike)
    if case.strike > 1e8:
        raise Stage99Blocked("Synthetic strike exceeds permitted preflight bounds")
    if case.strike * case.quantity > MAX_SYNTHETIC_NOTIONAL_INR:
        raise Stage99Blocked("Synthetic strike notional exceeds bounded numerical safety limit")
    if (contract.group(3) != case.option_type or contract.group(4) is None or
            float(contract.group(4)) != case.strike):
        raise Stage99Blocked("Option type/strike does not match synthetic contract identifier")
    if (case.instrument_type == "OPTIONS_LONG" and case.position_side != "LONG") or (
        case.instrument_type == "OPTIONS_SHORT" and case.position_side != "SHORT"
    ):
        raise Stage99Blocked("Option instrument and position side conflict")
    settlement = settle_option_at_expiry(
        symbol=case.contract_id, option_type=case.option_type,
        side=case.position_side, settlement_spot=case.settlement_spot,
        strike=case.strike, quantity=case.quantity, entry_premium=case.entry_price,
        is_index_option=True,
    )
    margin = estimate_span_elm_margin(
        underlying_spot=case.settlement_spot, quantity=case.quantity,
        instrument_type=case.instrument_type, option_premium=case.entry_price,
        strike=case.strike, option_type=case.option_type,
    )
    return Stage99SyntheticReview(
        contract_id=case.contract_id, market="INDIAN_FO", currency="INR",
        instrument_type=case.instrument_type, lots=case.quantity // case.lot_size,
        settlement_mode=settlement.settlement_mode,
        is_exercised=settlement.exercised,
        synthetic_gross_pnl=settlement.gross_pnl,
        synthetic_net_pnl=settlement.net_pnl_after_exercise_stt,
        indicative_margin_blocked=margin.total_margin_blocked,
        evidence_note="Indicative option charges, exercise STT and settlement only; no authenticated exchange/broker evidence.",
    )


def review_dict(case: Stage99SyntheticCase) -> dict:
    """Emit auditable, JSON-serializable read-only synthetic review."""
    return asdict(review_synthetic_expiry_margin(case))
