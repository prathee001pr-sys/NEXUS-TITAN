"""Evidence adapters for the eight trading-specialist review lanes.

These are role contracts, not autonomous agents or signal generators. A role
can emit a directional proposal only when a caller supplies explicit,
traceable evidence and an invalidation condition. Missing evidence becomes HOLD.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from nexus_titan.intelligence.consensus import SignalProposal


SPECIALIST_ROLES: tuple[str, ...] = (
    "MARKET_STRUCTURE", "TREND_REGIME", "MOMENTUM", "VOLATILITY",
    "OPTIONS_FLOW", "LIQUIDITY_MICROSTRUCTURE", "EVENT_CONTEXT", "PORTFOLIO_RISK",
)


@dataclass(frozen=True, slots=True)
class SpecialistEvidence:
    role: str
    action: str
    reason: str
    evidence_ref: str
    invalidation: str

    def __post_init__(self) -> None:
        if self.role not in SPECIALIST_ROLES:
            raise ValueError(f"unknown specialist role: {self.role}")
        if self.action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("action must be BUY, SELL, or HOLD")
        for name in ("reason", "evidence_ref", "invalidation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")


def adapt_specialist_evidence(items: Iterable[SpecialistEvidence]) -> tuple[SignalProposal, ...]:
    """Validate role uniqueness/completeness and map supplied evidence to consensus.

    Missing roles are intentionally not fabricated. At least two independent
    directional role proposals are required by this adapter before consensus
    can consider a directional candidate.
    """
    evidence = tuple(items)
    seen: set[str] = set()
    evidence_sources: set[str] = set()
    proposals: list[SignalProposal] = []
    for item in evidence:
        if item.role in seen:
            raise ValueError(f"duplicate specialist role: {item.role}")
        seen.add(item.role)
        if item.action in {"BUY", "SELL"}:
            if item.evidence_ref in evidence_sources:
                raise ValueError("directional roles must cite independent evidence sources")
            evidence_sources.add(item.evidence_ref)
        proposals.append(SignalProposal(
            specialist_id=item.role, action=item.action, reason=item.reason,
            evidence_ref=item.evidence_ref, invalidation=item.invalidation,
        ))
    directional = sum(item.action in {"BUY", "SELL"} for item in evidence)
    if directional == 1:
        # Add a conservative HOLD lane: one opinion cannot become consensus.
        proposals.append(SignalProposal(
            specialist_id="INDEPENDENT_CONFIRMATION_REQUIRED", action="HOLD",
            reason="Only one directional specialist supplied evidence.",
            evidence_ref="internal:minimum-independent-confirmation",
            invalidation="A second independent, evidence-backed role agrees.",
        ))
    return tuple(proposals)
