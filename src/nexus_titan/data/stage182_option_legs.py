"""Stage 182: bounded same-expiry F&O option-leg metadata and premium audit.

Does NOT certify NSE lot sizes, expiry calendars, margin, or payoff boundaries.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class OptionLeg:
    symbol: str
    expiry: date
    option_type: str
    strike: str
    side: str
    lot_size: int
    lots: int
    entry_premium: str


def legs_digest(legs: tuple[OptionLeg, ...]) -> str:
    """Stable audit fingerprint for strictly validated leg fields (not source proof)."""
    rows = [f'{v.symbol}|{v.expiry.isoformat()}|{v.option_type}|{v.strike}|'
            f'{v.side}|{v.lot_size}|{v.lots}|{v.entry_premium}' for v in legs]
    return hashlib.sha256('\n'.join(rows).encode('ascii')).hexdigest()


@dataclass(frozen=True, slots=True)
class OptionLegReceipt:
    accepted: bool
    leg_count: int
    net_premium_cash: Decimal | None
    gross_premium_cash: Decimal | None
    legs_sha256: str
    blockers: tuple[str, ...]


def audit_option_legs(legs: tuple[OptionLeg, ...], *, asof: date,
                      lot_size_verified: bool) -> OptionLegReceipt:
    blockers: list[str] = []
    if type(asof) is not date or not isinstance(legs, tuple) or not 1 <= len(legs) <= 8:
        return OptionLegReceipt(False, 0, None, None, '', ('invalid asof or leg count',))
    if lot_size_verified is not True:
        blockers.append('unverified contract lot sizes')
    net = gross = Decimal('0')
    identities: set[tuple[str, date, str, Decimal]] = set()
    reference: tuple[str, date] | None = None
    for idx, leg in enumerate(legs):
        if not isinstance(leg, OptionLeg):
            blockers.append(f'leg {idx}: invalid record')
            continue
        try:
            if (leg.symbol not in ('NIFTY', 'BANKNIFTY') or type(leg.expiry) is not date
                    or leg.expiry < asof or leg.option_type not in ('CE', 'PE')
                    or leg.side not in ('BUY', 'SELL') or type(leg.lot_size) is not int
                    or not 1 <= leg.lot_size <= 100_000 or type(leg.lots) is not int
                    or not 1 <= leg.lots <= 10_000):
                raise ValueError('invalid option metadata')
            strike, premium = parse_amount(leg.strike), parse_amount(leg.entry_premium)
            if strike <= 0 or premium <= 0:
                raise ValueError('nonpositive strike or premium')
            identity = (leg.symbol, leg.expiry, leg.option_type, strike)
            if identity in identities:
                raise ValueError('duplicate contract')
            identities.add(identity)
            scope = (leg.symbol, leg.expiry)
            if reference is None:
                reference = scope
            if scope != reference:
                raise ValueError('mixed underlying or expiry')
            cash = premium * leg.lot_size * leg.lots
            gross += cash
            net += cash if leg.side == 'SELL' else -cash
        except (ValueError, TypeError, OverflowError):
            blockers.append(f'leg {idx}: invalid metadata or duplicate')
    fingerprint = legs_digest(legs) if not blockers else ''
    return OptionLegReceipt(not blockers, len(legs), net if not blockers else None,
                            gross if not blockers else None, fingerprint, tuple(blockers[:24]))
