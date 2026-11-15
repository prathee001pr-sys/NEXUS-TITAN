from datetime import datetime, timezone, timedelta

import pytest

from nexus_titan.operations import (
    HealthMonitor, ResourceBudget, ResourceManager, ResourceUsage, evaluate_watchdog,
)


def test_health_monitor_healthy_then_stale_then_critical():
    monitor = HealthMonitor(stale_after_seconds=10, critical_after_seconds=30, failure_threshold=2)
    base = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    monitor.heartbeat("market-data", base)
    assert monitor.evaluate(now=base + timedelta(seconds=2)).status == "HEALTHY"
    stale = monitor.evaluate(now=base + timedelta(seconds=11))
    assert stale.status == "STALE"
    assert evaluate_watchdog(stale).action == "HOLD_NEW_RESEARCH_TASKS"
    critical = monitor.evaluate(now=base + timedelta(seconds=31))
    decision = evaluate_watchdog(critical)
    assert decision.action == "OPERATOR_RECOVERY_REQUIRED"
    assert decision.automated_restart is False
    assert decision.trading_control_changed is False
    assert decision.live_order_submitted is False


def test_health_monitor_failure_threshold_and_unknown_component():
    monitor = HealthMonitor(failure_threshold=2)
    monitor.record_failure("options-feed", "TimeoutError")
    monitor.record_failure("options-feed", "TimeoutError")
    report = monitor.evaluate(components=["options-feed", "broker-adapter"])
    states = {item.component: item.status for item in report.components}
    assert states["options-feed"] == "CRITICAL"
    assert states["broker-adapter"] == "UNKNOWN"


def test_health_monitor_requires_timezone_aware_timestamps():
    monitor = HealthMonitor()
    with pytest.raises(ValueError):
        monitor.heartbeat("component", datetime(2026, 11, 1, 10, 0))


def test_resource_manager_allows_throttles_and_rejects_without_killing_processes():
    manager = ResourceManager(ResourceBudget(max_concurrent_jobs=2, max_memory_mb=100, max_cpu_pct=80))
    assert manager.assess(ResourceUsage(1, 20, 30)).decision == "ALLOW"
    assert manager.assess(ResourceUsage(2, 20, 30)).decision == "THROTTLE"
    over = manager.assess(ResourceUsage(3, 120, 90))
    assert over.decision == "REJECT"
    assert over.process_termination_enabled is False


def test_resource_manager_rejects_invalid_metrics():
    manager = ResourceManager()
    with pytest.raises(ValueError):
        manager.assess(ResourceUsage(-1, 10, 10))
    with pytest.raises(ValueError):
        manager.assess(ResourceUsage(0, float("inf"), 10))
