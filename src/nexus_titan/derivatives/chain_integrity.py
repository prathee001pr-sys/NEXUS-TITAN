"""Opt-in fail-closed, point-in-time option-chain integrity gate.

This is a structural research gate, NOT verification of exchange/vendor identity.
Caller-provided source_verified is a declaration requiring external review.
No brokers, orders, strategy promotion, or production permissions are touched.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.derivatives.chain_and_settlement import (
    OptionChainQuote,
    inspect_option_chain_snapshot,
)

_INDIA = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class VerifiedChainIntegrityReport:
    quote_count: int
    issues: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _aligned(value: float, step: float) -> bool:
    """Check a decimal tick/strike grid without binary-float modulo errors."""
    try:
        ratio = Decimal(str(value)) / Decimal(str(step))
        return abs(ratio - ratio.to_integral_value()) <= Decimal("0.000001")
    except (InvalidOperation, ArithmeticError, ValueError):
        return False


def inspect_verified_option_chain(
    quotes: list[OptionChainQuote] | tuple[OptionChainQuote, ...],
    contract: PointInTimeContractSpec,
    *,
    observed_at: datetime,
    max_quote_age_seconds: float = 120.0,
    max_snapshot_skew_seconds: float = 2.0,
    max_spot_dispersion_pct: float = 0.5,
    require_call_put_pairs: bool = True,
) -> VerifiedChainIntegrityReport:
    """Check a homogeneous snapshot against explicitly sourced contract metadata.

    All clock/expiry dates are interpreted in Asia/Kolkata exchange-local time,
    not in the quote's arbitrary UTC-offset calendar date. An empty snapshot,
    missing official-source declaration, missing expiry, or bad metadata is
    rejected. Only one underlying/expiry/contract is allowed per invocation.

    This function is additive: the existing per-row structural validator runs
    first. Passing this check does not independently prove data rights, official
    exchange metadata, tradability, or historical accuracy.
    """
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    for name, limit, allow_zero in (
        ("max_quote_age_seconds", max_quote_age_seconds, True),
        ("max_snapshot_skew_seconds", max_snapshot_skew_seconds, True),
        ("max_spot_dispersion_pct", max_spot_dispersion_pct, True),
    ):
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    if not isinstance(require_call_put_pairs, bool):
        raise ValueError("require_call_put_pairs must be boolean")
    if not isinstance(contract, PointInTimeContractSpec):
        raise TypeError("contract must be a PointInTimeContractSpec")
    if not isinstance(quotes, (tuple, list)):
        raise TypeError("quotes must be a list or tuple")
    rows = tuple(quotes)
    issues = list(inspect_option_chain_snapshot(rows).errors)
    if not rows:
        issues.append("Empty option-chain snapshot")
    if contract.segment != "OPTIONS":
        issues.append("Point-in-time contract must have OPTIONS segment")
    if not contract.source_verified or not contract.source_reference:
        issues.append("Unverified point-in-time contract metadata (source evidence required)")
    if contract.expiry_date is None:
        issues.append("Point-in-time contract expiry_date is required")
    if (isinstance(contract.strike_step, bool) or
        not isinstance(contract.strike_step, (int, float)) or
        not math.isfinite(contract.strike_step) or contract.strike_step <= 0):
        issues.append("Invalid contract strike_step")
    local_date = observed_at.astimezone(_INDIA).date()
    if not contract.effective_from <= local_date <= contract.effective_to:
        issues.append("Contract metadata is not effective at observed_at")
    if contract.expiry_date is not None and local_date > contract.expiry_date:
        issues.append("Snapshot observed after contract expiry (India local date)")

    instants: list[datetime] = []
    spots: list[float] = []
    keys: set[tuple[str, date, str, Decimal]] = set()
    sides: dict[Decimal, set[str]] = {}
    for idx, q in enumerate(rows):
        if not isinstance(q, OptionChainQuote):
            continue  # Existing row validator reports this.
        try:
            when = datetime.fromisoformat(q.timestamp.replace("Z", "+00:00"))
            if when.tzinfo is None or when.utcoffset() is None:
                raise ValueError("timezone missing")
        except (TypeError, AttributeError, ValueError):
            issues.append(f"Row {idx}: invalid or timezone-naive quote timestamp")
            continue
        instants.append(when)
        quote_date = when.astimezone(_INDIA).date()
        if quote_date != local_date:
            issues.append(f"Row {idx}: quote and observation have different India trading dates")
        if not contract.effective_from <= quote_date <= contract.effective_to:
            issues.append(f"Row {idx}: quote outside contract effective window")
        if contract.expiry_date is not None and quote_date > contract.expiry_date:
            issues.append(f"Row {idx}: quote after contract expiry")
        lag_seconds = (observed_at - when).total_seconds()
        if lag_seconds < 0:
            issues.append(f"Row {idx}: quote timestamp is in the future")
        elif lag_seconds > max_quote_age_seconds:
            issues.append(f"Row {idx}: stale quote ({lag_seconds:.1f}s old)")

        if not isinstance(q.symbol, str) or q.symbol.strip().upper() != contract.symbol.strip().upper():
            issues.append(f"Row {idx}: symbol differs from contract metadata")
        if not isinstance(q.underlying, str) or q.underlying.strip().upper() != contract.underlying.strip().upper():
            issues.append(f"Row {idx}: underlying differs from contract metadata")
        try:
            expiry = date.fromisoformat(q.expiry_date)
        except (TypeError, ValueError):
            issues.append(f"Row {idx}: invalid expiry_date")
            continue
        if contract.expiry_date is None or expiry != contract.expiry_date:
            issues.append(f"Row {idx}: expiry differs from contract metadata")
        if q.lot_size != contract.lot_size:
            issues.append(f"Row {idx}: lot size differs from contract metadata")
        if isinstance(q.strike, bool) or not isinstance(q.strike, (int, float)) or not math.isfinite(q.strike) or q.strike <= 0:
            continue  # Existing row validator reports invalid prices.
        if (isinstance(contract.strike_step, (int, float)) and not isinstance(contract.strike_step, bool)
                and math.isfinite(contract.strike_step) and contract.strike_step > 0
                and not _aligned(q.strike, contract.strike_step)):
            issues.append(f"Row {idx}: strike not aligned to contract strike_step")
        for name in ("bid", "ask", "ltp"):
            price = getattr(q, name)
            if (isinstance(price, (int, float)) and not isinstance(price, bool)
                    and math.isfinite(price) and price > 0 and not _aligned(price, contract.tick_size)):
                issues.append(f"Row {idx}: {name} price not aligned to contract tick_size")

        strike = Decimal(str(q.strike))
        if q.option_type in ("CE", "PE"):
            key = (q.symbol.strip().upper() if isinstance(q.symbol, str) else "", expiry, q.option_type, strike)
            if key in keys:
                issues.append(f"Row {idx}: duplicate contract/strike/side in snapshot")
            keys.add(key)
            sides.setdefault(strike, set()).add(q.option_type)
        if isinstance(q.underlying_spot, (int, float)) and not isinstance(q.underlying_spot, bool):
            if math.isfinite(q.underlying_spot) and q.underlying_spot > 0:
                spots.append(float(q.underlying_spot))

    if len(instants) > 1 and (max(instants) - min(instants)).total_seconds() > max_snapshot_skew_seconds:
        issues.append("Quote timestamps exceed snapshot synchronization window")
    if spots and (max(spots) - min(spots)) / min(spots) * 100 > max_spot_dispersion_pct:
        issues.append("Inconsistent underlying spot across option-chain rows")
    if require_call_put_pairs:
        for strike, present in sides.items():
            if present != {"CE", "PE"}:
                issues.append(f"Missing CE/PE pair at strike {strike}")
    return VerifiedChainIntegrityReport(quote_count=len(rows), issues=tuple(issues))
