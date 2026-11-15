"""Conservative watchdog policy; reports actions but never restarts or trades."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nexus_titan.operations.health import HealthReport

WatchdogAction = Literal["NO_ACTION", "ALERT_OPERATOR", "HOLD_NEW_RESEARCH_TASKS", "OPERATOR_RECOVERY_REQUIRED"]


@dataclass(frozen=True)
class WatchdogDecision:
    action: WatchdogAction
    reasons: tuple[str, ...]
    automated_restart: bool = False
    trading_control_changed: bool = False
    live_order_submitted: bool = False


def evaluate_watchdog(report: HealthReport) -> WatchdogDecision:
    """Translate health states into advisory operational policy only."""
    if not isinstance(report, HealthReport):
        raise TypeError("report must be a HealthReport.")
    critical = [item.component for item in report.components if item.status == "CRITICAL"]
    stale = [item.component for item in report.components if item.status == "STALE"]
    degraded = [item.component for item in report.components if item.status == "DEGRADED"]
    unknown = [item.component for item in report.components if item.status == "UNKNOWN"]
    reasons: list[str] = []
    if critical:
        reasons.append("critical_components=" + ",".join(critical))
        action: WatchdogAction = "OPERATOR_RECOVERY_REQUIRED"
    elif stale:
        reasons.append("stale_components=" + ",".join(stale))
        action = "HOLD_NEW_RESEARCH_TASKS"
    elif degraded:
        reasons.append("degraded_components=" + ",".join(degraded))
        action = "ALERT_OPERATOR"
    elif unknown:
        reasons.append("unknown_components=" + ",".join(unknown))
        action = "ALERT_OPERATOR"
    else:
        action = "NO_ACTION"
        reasons.append("all_monitored_components_healthy")
    return WatchdogDecision(action, tuple(reasons))
