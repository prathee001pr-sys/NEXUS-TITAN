"""Stage 181: deterministic, read-only synthetic order lifecycle reconciliation.

No broker adapter, live order, or permission to execute is provided.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class OrderEvent:
    event_id: str
    order_id: str
    kind: str
    at: datetime
    fill_quantity: str = '0'


@dataclass(frozen=True, slots=True)
class OrderLifecycleReceipt:
    accepted: bool
    final_state: str
    filled_quantity: Decimal | None
    blockers: tuple[str, ...]


def audit_order_lifecycle(order_id: str, requested_quantity: str,
                          events: tuple[OrderEvent, ...]) -> OrderLifecycleReceipt:
    """Require SUBMITTED, bounded strictly timed events, and terminal disposition.

    A partially filled cancellation may be a valid *record* but is not fully
    filled; downstream research gates must check final_state == 'FILLED'.
    """
    if not isinstance(order_id, str) or not 1 <= len(order_id) <= 128 or not order_id.strip():
        return OrderLifecycleReceipt(False, 'INVALID', None, ('invalid order id',))
    try:
        requested = parse_amount(requested_quantity)
    except ValueError:
        return OrderLifecycleReceipt(False, 'INVALID', None, ('invalid requested quantity',))
    if requested <= 0 or not isinstance(events, tuple) or not 2 <= len(events) <= 10000:
        return OrderLifecycleReceipt(False, 'INVALID', None, ('invalid quantity or event count',))
    seen: set[str] = set()
    filled = Decimal('0')
    prev: datetime | None = None
    state = 'NEW'
    errors: list[str] = []
    for idx, event in enumerate(events):
        if not isinstance(event, OrderEvent):
            errors.append(f'event {idx}: invalid type')
            break
        if (event.order_id != order_id or not isinstance(event.event_id, str)
                or not 1 <= len(event.event_id) <= 128 or not event.event_id.strip()):
            errors.append(f'event {idx}: invalid identity')
            break
        if event.event_id in seen:
            errors.append(f'event {idx}: replayed event')
            break
        seen.add(event.event_id)
        if not isinstance(event.at, datetime) or event.at.tzinfo is None or event.at.utcoffset() is None:
            errors.append(f'event {idx}: timezone required')
            break
        stamp = event.at.astimezone(timezone.utc)
        if prev is not None and stamp <= prev:
            errors.append(f'event {idx}: time reversal or collision')
            break
        prev = stamp
        try:
            qty = parse_amount(event.fill_quantity)
        except ValueError:
            errors.append(f'event {idx}: invalid fill quantity')
            break
        if state == 'NEW' and event.kind == 'SUBMITTED' and qty == 0:
            state = 'OPEN'
        elif state == 'OPEN' and event.kind == 'FILL' and qty > 0:
            filled += qty
            if filled > requested:
                errors.append(f'event {idx}: overfill')
                break
            if filled == requested:
                state = 'FILLED'
        elif state == 'OPEN' and event.kind == 'CANCELLED' and qty == 0:
            state = 'CANCELLED'
        elif state == 'OPEN' and event.kind == 'REJECTED' and qty == 0 and filled == 0:
            state = 'REJECTED'
        else:
            errors.append(f'event {idx}: illegal order transition')
            break
    if not errors and state == 'OPEN':
        errors.append('unterminated order')
    return OrderLifecycleReceipt(not errors, state, filled, tuple(errors))
