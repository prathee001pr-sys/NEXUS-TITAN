"""Stage 173: exact Decimal closed round-trip P&L, offline only.

Caller must supply all applicable taxes/fees; this does not calculate Indian STT,
GST, SEBI, stamp duty, broker tariff, contract eligibility, or real fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

_AMOUNT = re.compile(r'^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?$')


@dataclass(frozen=True, slots=True)
class SettlementReceipt:
    accepted: bool
    gross_pnl: Decimal | None
    net_pnl: Decimal | None
    blockers: tuple[str, ...]


def _amount(value: str) -> Decimal:
    if not isinstance(value, str) or not _AMOUNT.fullmatch(value):
        raise ValueError('amount must be a bounded nonnegative decimal string')
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid amount') from exc
    if not n.is_finite():
        raise ValueError('non-finite amount')
    return n


def audit_roundtrip_settlement(
    *, entry_side: str, entry_price: str, exit_price: str,
    quantity: str, contract_multiplier: int, entry_fees: str, exit_fees: str,
) -> SettlementReceipt:
    """Net P&L of exactly one fully closed long (BUY) or short (SELL) lot.

    `quantity` denotes contracts, while `contract_multiplier` denotes units
    per contract. This function never assumes a strategy is profitable or safe.
    """
    if entry_side not in ('BUY', 'SELL') or type(contract_multiplier) is not int or not 1 <= contract_multiplier <= 1_000_000:
        return SettlementReceipt(False, None, None, ('invalid side or multiplier',))
    try:
        entry = _amount(entry_price)
        exit_ = _amount(exit_price)
        qty = _amount(quantity)
        fee_in = _amount(entry_fees)
        fee_out = _amount(exit_fees)
        if entry <= 0 or exit_ <= 0 or qty <= 0:
            raise ValueError('nonpositive price or quantity')
        units = qty * contract_multiplier
        gross = (exit_ - entry if entry_side == 'BUY' else entry - exit_) * units
        net = gross - fee_in - fee_out
    except (ValueError, InvalidOperation):
        return SettlementReceipt(False, None, None, ('invalid amount',))
    return SettlementReceipt(True, gross, net, ())
