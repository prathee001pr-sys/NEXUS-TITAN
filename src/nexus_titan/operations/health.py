"""Dependency-free component heartbeat and health evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

HealthStatus = Literal["HEALTHY", "DEGRADED", "STALE", "CRITICAL", "UNKNOWN"]


def _aware(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ComponentHealth:
    component: str
    status: HealthStatus
    last_heartbeat: str | None
    heartbeat_age_seconds: float | None
    consecutive_failures: int
    last_error_type: str | None = None


@dataclass(frozen=True)
class HealthReport:
    status: HealthStatus
    components: tuple[ComponentHealth, ...]
    checked_at: str


class HealthMonitor:
    """Tracks explicit component heartbeats; it does not restart or control services."""

    def __init__(self, *, stale_after_seconds: float = 30.0, critical_after_seconds: float = 90.0,
                 failure_threshold: int = 3) -> None:
        if not (0 < stale_after_seconds < critical_after_seconds):
            raise ValueError("heartbeat thresholds must satisfy 0 < stale < critical.")
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int) or failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer.")
        self.stale_after_seconds = float(stale_after_seconds)
        self.critical_after_seconds = float(critical_after_seconds)
        self.failure_threshold = failure_threshold
        self._heartbeats: dict[str, datetime] = {}
        self._failures: dict[str, tuple[int, str | None]] = {}

    def heartbeat(self, component: str, at: datetime | str | None = None) -> None:
        name = self._name(component)
        stamp = _aware(at or datetime.now(timezone.utc))
        self._heartbeats[name] = stamp
        self._failures[name] = (0, None)

    def record_failure(self, component: str, error_type: str) -> None:
        name = self._name(component)
        if not isinstance(error_type, str) or not error_type.strip():
            raise ValueError("error_type is required.")
        count, _ = self._failures.get(name, (0, None))
        self._failures[name] = (count + 1, error_type.strip()[:100])

    def evaluate(self, *, components: tuple[str, ...] | list[str] | None = None,
                 now: datetime | str | None = None) -> HealthReport:
        checked = _aware(now or datetime.now(timezone.utc))
        names = sorted(set(components or tuple(self._heartbeats) + tuple(self._failures)))
        entries: list[ComponentHealth] = []
        for name in names:
            name = self._name(name)
            stamp = self._heartbeats.get(name)
            failures, last_error = self._failures.get(name, (0, None))
            if stamp is None:
                age = None
                if failures >= self.failure_threshold:
                    status: HealthStatus = "CRITICAL"
                elif failures > 0:
                    status = "DEGRADED"
                else:
                    status = "UNKNOWN"
            else:
                age = (checked - stamp).total_seconds()
                if age < 0:
                    status = "CRITICAL"
                elif age >= self.critical_after_seconds or failures >= self.failure_threshold:
                    status = "CRITICAL"
                elif age >= self.stale_after_seconds or failures > 0:
                    status = "STALE" if age >= self.stale_after_seconds else "DEGRADED"
                else:
                    status = "HEALTHY"
            entries.append(ComponentHealth(name, status, stamp.isoformat() if stamp else None,
                                           round(age, 3) if age is not None else None,
                                           failures, last_error))
        statuses = [entry.status for entry in entries]
        overall: HealthStatus = "HEALTHY"
        for status in ("CRITICAL", "STALE", "DEGRADED", "UNKNOWN"):
            if status in statuses:
                overall = status
                break
        return HealthReport(overall, tuple(entries), checked.isoformat())

    @staticmethod
    def _name(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("component name is required.")
        return value.strip()
