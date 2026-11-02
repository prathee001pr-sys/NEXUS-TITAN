"""Deterministic adversarial checks for a proposed trade; advisory only."""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class TradeProposal:
    side: str
    entry: float
    stop: float
    target: float | None
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    expected_edge_bps: float = 0.0
    liquidity_available: float | None = None
    order_quantity: float = 0.0


@dataclass(frozen=True)
class RedTeamFinding:
    scenario: str
    severity: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RedTeamReport:
    findings: tuple[RedTeamFinding, ...]
    veto_recommended: bool
    order_submitted: bool = False


def challenge_trade(proposal: TradeProposal) -> RedTeamReport:
    findings: list[RedTeamFinding] = []
    numeric = (proposal.entry, proposal.stop, proposal.spread_bps,
               proposal.slippage_bps, proposal.expected_edge_bps, proposal.order_quantity)
    valid = (proposal.side.upper() in {"BUY", "SELL"}
             and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in numeric)
             and proposal.entry > 0 and proposal.stop > 0
             and proposal.spread_bps >= 0 and proposal.slippage_bps >= 0
             and proposal.order_quantity > 0)
    findings.append(RedTeamFinding("input_integrity", "critical", valid,
                                   "Proposal fields are valid." if valid else "Malformed or non-finite trade inputs."))
    if valid:
        stop_valid = proposal.stop < proposal.entry if proposal.side.upper() == "BUY" else proposal.stop > proposal.entry
        findings.append(RedTeamFinding("adverse_price_move", "critical", stop_valid,
                                       "Protective stop is on the adverse side." if stop_valid else "Stop is not protective for this direction."))
        friction = proposal.spread_bps + proposal.slippage_bps
        edge_valid = proposal.expected_edge_bps > friction
        findings.append(RedTeamFinding("spread_slippage_stress", "high", edge_valid,
                                       f"Expected edge {proposal.expected_edge_bps:.2f} bps vs estimated friction {friction:.2f} bps."))
        if proposal.liquidity_available is not None:
            liquidity_valid = (math.isfinite(proposal.liquidity_available)
                               and proposal.liquidity_available >= proposal.order_quantity)
            findings.append(RedTeamFinding("liquidity_gap", "high", liquidity_valid,
                                           "Displayed liquidity covers requested quantity." if liquidity_valid else "Displayed liquidity is insufficient or invalid."))
        if proposal.target is not None:
            target_valid = (proposal.target > proposal.entry if proposal.side.upper() == "BUY" else proposal.target < proposal.entry)
            findings.append(RedTeamFinding("target_direction", "medium", target_valid,
                                           "Target is directionally consistent." if target_valid else "Target is on the wrong side of entry."))
    return RedTeamReport(tuple(findings), any(not f.passed and f.severity in {"critical", "high"} for f in findings), False)
