"""Stage 171: fail-closed quote-age and synthetic execution-timing checks.

This is an offline consistency audit, NOT a broker adapter or live authorization.
Timestamps must represent the same real instants (timezone-aware datetimes).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class TimingReceipt:
    accepted: bool
    blockers: tuple[str, ...]


def audit_execution_timing(
    *, observation_at: datetime, decision_at: datetime,
    submitted_at: datetime, filled_at: datetime,
    max_observation_age_ms: int, max_execution_latency_ms: int,
) -> TimingReceipt:
    """Reject lookahead, stale quotes, time reversal, or excessive simulated delay.

    `observation_at` is when the observed price became available, NOT when a
    candle started. Calling code is responsible for correctly marking bar close.
    """
    limits = (max_observation_age_ms, max_execution_latency_ms)
    if any(type(n) is not int or not 0 <= n <= 86_400_000 for n in limits):
        return TimingReceipt(False, ('invalid timing limits',))
    stamps = (observation_at, decision_at, submitted_at, filled_at)
    if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in stamps):
        return TimingReceipt(False, ('timezone-aware timestamps required',))
    obs, decision, submitted, filled = (t.astimezone(timezone.utc) for t in stamps)
    issues = []
    if obs > decision:
        issues.append('future observation / lookahead')
    if decision > submitted:
        issues.append('order submitted before decision')
    if submitted > filled:
        issues.append('fill before submission')
    if obs <= decision and decision - obs > timedelta(milliseconds=max_observation_age_ms):
        issues.append('stale market observation')
    if submitted <= filled and filled - submitted > timedelta(milliseconds=max_execution_latency_ms):
        issues.append('excessive execution latency')
    return TimingReceipt(not issues, tuple(issues))
