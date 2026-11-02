"""Deterministic, append-only evidence ledger for multi-session shadow validation.

This module records simulated observations only. It has no broker adapter and cannot
submit orders. Reconciliation compares caller-supplied snapshots; it does not certify
exchange fills, statutory charges, or live account balances.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Iterable


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _money(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return round(float(value), 2)


@dataclass(frozen=True)
class ShadowEvent:
    session_date: str
    timestamp: str
    event_type: str
    reference: str
    payload: dict


@dataclass(frozen=True)
class Reconciliation:
    session_date: str
    expected_closing_balance: float
    observed_closing_balance: float
    balance_difference: float
    expected_event_count: int
    observed_event_count: int
    is_reconciled: bool
    status: str


class ShadowEvidenceLedger:
    """Append-only JSONL evidence log with monotonic timestamps and hash chaining."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_timestamp: datetime | None = None
        self._last_hash = "0" * 64
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                digest = record.pop("record_hash")
                canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
                if hashlib.sha256(canonical.encode()).hexdigest() != digest:
                    raise ValueError("evidence ledger hash verification failed")
                if record["previous_hash"] != self._last_hash:
                    raise ValueError("evidence ledger chain verification failed")
                self._last_hash = digest
                self._last_timestamp = _timestamp(record["event"]["timestamp"])

    def append(self, event: ShadowEvent) -> str:
        parsed = _timestamp(event.timestamp)
        if self._last_timestamp and parsed < self._last_timestamp:
            raise ValueError("event timestamps must be monotonic")
        try:
            day = date.fromisoformat(event.session_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("session_date must be ISO YYYY-MM-DD") from exc
        if parsed.astimezone(ZoneInfo("Asia/Kolkata")).date() != day:
            raise ValueError("event timestamp must fall on the declared India session date")
        if not event.event_type or not event.reference:
            raise ValueError("event_type and reference are required")
        record = {"previous_hash": self._last_hash, "event": asdict(event)}
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({**record, "record_hash": digest}, sort_keys=True, allow_nan=False) + "\n")
        self._last_hash, self._last_timestamp = digest, parsed
        return digest

    def events(self, session_date: str | None = None) -> tuple[ShadowEvent, ...]:
        if not self.path.exists():
            return ()
        result = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)["event"]
            if session_date is None or row["session_date"] == session_date:
                result.append(ShadowEvent(**row))
        return tuple(result)


def reconcile_session(
    *, session_date: str, opening_balance: float, closing_balance: float,
    realized_pnl: float, fees: float, expected_event_count: int,
    observed_event_count: int, tolerance: float = 0.01,
) -> Reconciliation:
    """Reconcile a virtual session using closing = opening + realized P&L - fees."""
    opening = _money(opening_balance, "opening_balance")
    closing = _money(closing_balance, "closing_balance")
    pnl = _money(realized_pnl, "realized_pnl")
    charges = _money(fees, "fees")
    tol = _money(tolerance, "tolerance")
    if not isinstance(session_date, str):
        raise ValueError("session_date must be ISO YYYY-MM-DD")
    try:
        date.fromisoformat(session_date)
    except ValueError as exc:
        raise ValueError("session_date must be ISO YYYY-MM-DD") from exc
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
           for v in (expected_event_count, observed_event_count)) or tol < 0:
        raise ValueError("counts and tolerance must be non-negative")
    expected = round(opening + pnl - charges, 2)
    difference = round(closing - expected, 2)
    balanced = abs(difference) <= tol and expected_event_count == observed_event_count
    return Reconciliation(
        session_date=session_date, expected_closing_balance=expected,
        observed_closing_balance=closing, balance_difference=difference,
        expected_event_count=expected_event_count, observed_event_count=observed_event_count,
        is_reconciled=balanced, status="RECONCILED" if balanced else "REVIEW_REQUIRED",
    )


def evaluate_shadow_readiness(
    *, session_count: int, reconciled_sessions: int, closed_trades: int,
    data_provenance_verified: bool, execution_calibration_verified: bool,
    minimum_sessions: int = 20, minimum_trades: int = 30,
) -> dict:
    """Evidence gate only; it never promotes strategies or enables live trading."""
    values = (session_count, reconciled_sessions, closed_trades, minimum_sessions, minimum_trades)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise ValueError("counts and thresholds must be non-negative integers")
    checks = {
        "minimum_sessions": session_count >= minimum_sessions,
        "all_sessions_reconciled": reconciled_sessions == session_count,
        "minimum_closed_trades": closed_trades >= minimum_trades,
        "licensed_data_provenance": bool(data_provenance_verified),
        "execution_calibration": bool(execution_calibration_verified),
    }
    return {
        "eligible_for_human_review": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "strategy_promotion": "NOT_AUTOMATIC",
        "live_trading": "DISABLED",
    }
