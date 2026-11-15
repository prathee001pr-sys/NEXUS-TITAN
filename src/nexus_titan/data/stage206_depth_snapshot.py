"""Stage 206: bounded synthetic order-book depth at a causal decision instant.

This validates *caller-supplied* levels; it does NOT authenticate exchange feeds,
liquidity, contracts, or permission to submit orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re

from .stage176_quote_sanity import parse_amount

_ID = re.compile(r'[A-Za-z0-9:_-]{3,100}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: str
    quantity: int


@dataclass(frozen=True, slots=True)
class DepthSnapshot:
    snapshot_id: str
    contract_id: str
    dataset_sha256: str
    observed_at: datetime
    available_at: datetime
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]


@dataclass(frozen=True, slots=True)
class DepthSnapshotReceipt:
    accepted: bool
    snapshot_sha256: str
    contract_id: str
    dataset_sha256: str
    available_at: datetime | None
    decision_at: datetime | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    spread_bps: Decimal | None
    bid_quantity: int
    ask_quantity: int
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone aware timestamp required')
    return value.astimezone(timezone.utc)


def audit_depth_snapshot(snapshot: DepthSnapshot, *, decision_at: datetime,
                         tick_size: str, max_age_ms: int = 1500,
                         max_spread_bps: int = 1000) -> DepthSnapshotReceipt:
    errors: list[str] = []
    blank = lambda: DepthSnapshotReceipt(False, '', '', '', None, None, None, None, None, 0, 0, tuple(errors))
    if type(snapshot) is not DepthSnapshot:
        errors.append('invalid depth snapshot type')
        return blank()
    if (not isinstance(snapshot.snapshot_id, str) or not _ID.fullmatch(snapshot.snapshot_id)
            or not isinstance(snapshot.contract_id, str) or not _ID.fullmatch(snapshot.contract_id)
            or not isinstance(snapshot.dataset_sha256, str) or not _SHA.fullmatch(snapshot.dataset_sha256)):
        errors.append('invalid snapshot identity or dataset digest')
    if (type(max_age_ms) is not int or not 0 <= max_age_ms <= 86_400_000
            or type(max_spread_bps) is not int or not 0 <= max_spread_bps <= 10000):
        errors.append('invalid quote limits')
    try:
        observed, available, decision = map(_utc, (snapshot.observed_at, snapshot.available_at, decision_at))
        if observed > available or available > decision:
            errors.append('future or out-of-order depth clock')
        if type(max_age_ms) is int and 0 <= max_age_ms <= 86_400_000 and decision - available > timedelta(milliseconds=max_age_ms):
            errors.append('stale depth at decision')
    except (TypeError, ValueError, OverflowError):
        errors.append('invalid depth clock')
        observed = available = decision = None
    try:
        tick = parse_amount(tick_size)
        if tick <= 0:
            raise ValueError('nonpositive tick')
    except (ValueError, TypeError):
        tick = None
        errors.append('invalid tick size')
    parsed: list[list[tuple[Decimal, int]]] = []
    for side_name, levels in (('bid', snapshot.bids), ('ask', snapshot.asks)):
        side: list[tuple[Decimal, int]] = []
        if not isinstance(levels, tuple) or not 1 <= len(levels) <= 10:
            errors.append(f'invalid {side_name} depth level count')
            parsed.append(side)
            continue
        for idx, level in enumerate(levels):
            try:
                if type(level) is not DepthLevel or type(level.quantity) is not int or not 1 <= level.quantity <= 1_000_000:
                    raise ValueError('invalid level/quantity')
                price = parse_amount(level.price)
                if price <= 0 or tick is None or price % tick != 0:
                    raise ValueError('invalid or off-tick level')
                if side and not ((price < side[-1][0]) if side_name == 'bid' else (price > side[-1][0])):
                    raise ValueError('unsorted or duplicate level')
                side.append((price, level.quantity))
            except (ValueError, TypeError, ArithmeticError):
                errors.append(f'{side_name} level {idx}: invalid, duplicate or off-tick')
                break
        parsed.append(side)
    bids, asks = parsed
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    spread = None
    if best_bid is not None and best_ask is not None:
        if best_ask < best_bid:
            errors.append('crossed depth')
        else:
            midpoint = (best_bid + best_ask) / 2
            spread = (best_ask - best_bid) * 10000 / midpoint
            if type(max_spread_bps) is int and spread > max_spread_bps:
                errors.append('spread exceeds policy')
    if errors:
        return blank()
    body = {'id': snapshot.snapshot_id, 'contract': snapshot.contract_id,
            'dataset': snapshot.dataset_sha256, 'observed': observed.isoformat(timespec='microseconds'),
            'available': available.isoformat(timespec='microseconds'),
            'decision': decision.isoformat(timespec='microseconds'),
            'tick': str(tick.normalize()), 'age_ms': max_age_ms, 'spread_limit': max_spread_bps,
            'bids': [(str(p.normalize()), q) for p, q in bids],
            'asks': [(str(p.normalize()), q) for p, q in asks]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
    return DepthSnapshotReceipt(True, digest, snapshot.contract_id, snapshot.dataset_sha256,
                                available, decision, best_bid, best_ask, spread,
                                sum(q for _, q in bids), sum(q for _, q in asks), ())
