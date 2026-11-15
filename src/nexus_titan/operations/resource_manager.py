"""Advisory resource budgeting for research workloads; never kills processes."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

ResourceDecision = Literal["ALLOW", "THROTTLE", "REJECT"]


@dataclass(frozen=True)
class ResourceBudget:
    max_concurrent_jobs: int = 2
    max_memory_mb: float = 1024.0
    max_cpu_pct: float = 85.0

    def __post_init__(self) -> None:
        if isinstance(self.max_concurrent_jobs, bool) or not isinstance(self.max_concurrent_jobs, int) or self.max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be a positive integer.")
        for name in ("max_memory_mb", "max_cpu_pct"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")
        if self.max_cpu_pct > 100:
            raise ValueError("max_cpu_pct cannot exceed 100.")


@dataclass(frozen=True)
class ResourceUsage:
    active_jobs: int
    memory_mb: float
    cpu_pct: float


@dataclass(frozen=True)
class ResourceAssessment:
    decision: ResourceDecision
    reasons: tuple[str, ...]
    available_job_slots: int
    process_termination_enabled: bool = False


class ResourceManager:
    """Evaluate externally sampled usage against a bounded research budget."""

    def __init__(self, budget: ResourceBudget | None = None) -> None:
        self.budget = budget or ResourceBudget()

    def assess(self, usage: ResourceUsage) -> ResourceAssessment:
        if not isinstance(usage, ResourceUsage):
            raise TypeError("usage must be a ResourceUsage.")
        if isinstance(usage.active_jobs, bool) or not isinstance(usage.active_jobs, int) or usage.active_jobs < 0:
            raise ValueError("active_jobs must be a non-negative integer.")
        for name in ("memory_mb", "cpu_pct"):
            value = getattr(usage, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative.")
        reasons = []
        if usage.active_jobs >= self.budget.max_concurrent_jobs:
            reasons.append("concurrent_job_limit_reached")
        if usage.memory_mb >= self.budget.max_memory_mb:
            reasons.append("memory_budget_reached")
        if usage.cpu_pct >= self.budget.max_cpu_pct:
            reasons.append("cpu_budget_reached")
        over = (usage.active_jobs > self.budget.max_concurrent_jobs
                or usage.memory_mb > self.budget.max_memory_mb
                or usage.cpu_pct > self.budget.max_cpu_pct)
        if over:
            decision: ResourceDecision = "REJECT"
        elif reasons:
            decision = "THROTTLE"
        else:
            decision = "ALLOW"
        return ResourceAssessment(decision, tuple(reasons),
                                  max(0, self.budget.max_concurrent_jobs - usage.active_jobs))
