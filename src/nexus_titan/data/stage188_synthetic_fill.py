"""Stage 188: synthetic depth-bounded deterministic fill replay, never real orders."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
from .stage176_quote_sanity import parse_amount
from .stage187_causal_signal import CausalSignalReceipt


@dataclass(frozen=True, slots=True)
class SyntheticFillEvent:
    event_id: str
    signal_id: str
    filled_at: datetime
    quantity: int
    execution_price: str


@dataclass(frozen=True, slots=True)
class SyntheticFillReceipt:
    accepted: bool
    fully_filled: bool
    signal_id: str
    contract_id: str
    dataset_sha256: str
    tape_sha256: str
    side: str
    quantity: int
    average_price: Decimal | None
    last_fill_at: datetime | None
    fills_sha256: str
    blockers: tuple[str, ...]


def audit_synthetic_fills(events: tuple[SyntheticFillEvent, ...], *,
                          signal: CausalSignalReceipt, max_latency_ms: int = 5000) -> SyntheticFillReceipt:
    blockers: list[str] = []
    if (not isinstance(signal, CausalSignalReceipt) or not signal.accepted or signal.blockers
            or signal.decision_at is None or signal.bid is None or signal.ask is None):
        blockers.append('invalid causal signal')
    if type(max_latency_ms) is not int or not 0 <= max_latency_ms <= 86_400_000:
        blockers.append('invalid latency bound')
    if not isinstance(events, tuple) or not 1 <= len(events) <= 1000:
        blockers.append('invalid fill count')
    if blockers:
        return SyntheticFillReceipt(False, False, '', '', '', '', '', 0, None, None, '', tuple(blockers))
    slippage = Decimal(signal.max_slippage_bps) / Decimal(10000)
    low = signal.bid * (1 - slippage) if signal.side == 'SELL' else signal.bid
    high = signal.ask * (1 + slippage) if signal.side == 'BUY' else signal.ask
    depth = signal.ask_depth if signal.side == 'BUY' else signal.bid_depth
    seen: set[str] = set()
    last = signal.decision_at
    quantity = 0
    notional = Decimal(0)
    canonical: list[tuple[str, str, int, str]] = []
    for index, event in enumerate(events):
        if not isinstance(event, SyntheticFillEvent):
            blockers.append(f'fill {index}: invalid type')
            break
        try:
            if (not isinstance(event.event_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', event.event_id)
                    or event.event_id in seen or event.signal_id != signal.signal_id
                    or type(event.quantity) is not int or event.quantity <= 0):
                raise ValueError('invalid fill identity or quantity')
            if not isinstance(event.filled_at, datetime) or event.filled_at.tzinfo is None or event.filled_at.utcoffset() is None:
                raise ValueError('missing fill clock')
            stamp = event.filled_at.astimezone(timezone.utc)
            if stamp <= last or stamp - signal.decision_at > timedelta(milliseconds=max_latency_ms):
                raise ValueError('future, stale, or nonmonotonic fill')
            price = parse_amount(event.execution_price)
            if not low <= price <= high or price <= 0:
                raise ValueError('unrealistic synthetic execution price')
            quantity += event.quantity
            if quantity > signal.quantity or quantity > depth:
                raise ValueError('overfill or unavailable quote depth')
            seen.add(event.event_id)
            notional += event.quantity * price
            last = stamp
            canonical.append((event.event_id, stamp.isoformat(timespec='microseconds'), event.quantity, str(price.normalize())))
        except (ValueError, TypeError, OverflowError):
            blockers.append(f'fill {index}: invalid, out-of-order, or outside quote constraints')
            break
    digest = hashlib.sha256(json.dumps({'signal': signal.signal_id, 'tape': signal.tape_sha256,
                                       'fills': canonical}, separators=(',', ':')).encode('ascii')).hexdigest() if not blockers else ''
    return SyntheticFillReceipt(not blockers, not blockers and quantity == signal.quantity,
                                signal.signal_id, signal.contract_id, signal.dataset_sha256,
                                signal.tape_sha256, signal.side, quantity,
                                notional / quantity if quantity and not blockers else None,
                                last if not blockers else None, digest, tuple(blockers))
