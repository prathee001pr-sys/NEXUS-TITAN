"""Stage 172: duplicate-fill/replayed-event guard for offline execution records."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReplayReceipt:
    accepted: bool
    event_count: int
    blockers: tuple[str, ...]


def audit_event_replay(
    events: tuple[tuple[str, str, int], ...], *, max_events: int = 100_000,
) -> ReplayReceipt:
    """Each event is (immutable_event_id, order_id, per_order_sequence).

    Requires unique event IDs and strictly increasing sequences for each order.
    Does not contact brokers or assert that the source ledger is authentic.
    """
    if type(max_events) is not int or not 1 <= max_events <= 1_000_000:
        return ReplayReceipt(False, 0, ('invalid event limit',))
    if not isinstance(events, tuple) or not 0 < len(events) <= max_events:
        return ReplayReceipt(False, 0, ('missing or oversized events',))
    seen_ids: set[str] = set()
    order_seq: dict[str, int] = {}
    issues: list[str] = []
    for idx, event in enumerate(events):
        if not isinstance(event, tuple) or len(event) != 3:
            issues.append(f'event {idx}: invalid record')
            continue
        event_id, order_id, sequence = event
        if (not isinstance(event_id, str) or not 1 <= len(event_id) <= 128
            or not event_id.strip() or not isinstance(order_id, str)
            or not 1 <= len(order_id) <= 128 or not order_id.strip()
            or type(sequence) is not int or sequence < 0):
            issues.append(f'event {idx}: invalid fields')
            continue
        if event_id in seen_ids:
            issues.append(f'event {idx}: duplicate event id')
        seen_ids.add(event_id)
        if order_id in order_seq and sequence <= order_seq[order_id]:
            issues.append(f'event {idx}: duplicate or reversed order sequence')
        order_seq[order_id] = sequence
    return ReplayReceipt(not issues, len(events), tuple(issues[:32]))
