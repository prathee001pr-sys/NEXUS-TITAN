"""Conservative signal consensus; never substitutes for independent risk veto."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .market_state import MarketState


class Decision(StrEnum):
    TRADE_CANDIDATE = "TRADE CANDIDATE"
    NO_TRADE = "NO TRADE"
    DATA_INVALID = "DATA INVALID"
    WAIT_FOR_CONFIRMATION = "WAIT FOR CONFIRMATION"


@dataclass(frozen=True, slots=True)
class SignalProposal:
    specialist_id: str
    action: str
    reason: str
    evidence_ref: str
    invalidation: str


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    decision: Decision
    action: str | None
    supporting_roles: tuple[str, ...]
    opposing_roles: tuple[str, ...]
    reasons: tuple[str, ...]
    confidence_label: str = "UNCALIBRATED"


class ConsensusEngine:
    """Requires valid state and independent role evidence; disagreement means wait."""

    VALID_ACTIONS = {"BUY", "SELL", "HOLD"}

    def evaluate(self, state: MarketState, proposals: Iterable[SignalProposal]) -> ConsensusResult:
        if not state.quality.valid:
            return ConsensusResult(Decision.DATA_INVALID, None, (), (), state.quality.warnings)
        items = tuple(proposals)
        if not items:
            return ConsensusResult(Decision.NO_TRADE, None, (), (), ("No specialist proposals supplied.",))
        for item in items:
            if (not item.specialist_id.strip() or item.action not in self.VALID_ACTIONS
                or not item.reason.strip() or not item.evidence_ref.strip() or not item.invalidation.strip()):
                return ConsensusResult(Decision.WAIT_FOR_CONFIRMATION, None, (), (),
                                       ("A proposal is incomplete or invalid; no signal inferred.",))
        directions = {item.action for item in items if item.action in {"BUY", "SELL"}}
        if not directions:
            return ConsensusResult(Decision.NO_TRADE, None, (), (), tuple(x.reason for x in items))
        if len(directions) > 1:
            return ConsensusResult(
                Decision.WAIT_FOR_CONFIRMATION, None,
                tuple(x.specialist_id for x in items if x.action in directions),
                tuple(x.specialist_id for x in items if x.action == "HOLD"),
                ("Specialist directions conflict; require more evidence.",),
            )
        action = next(iter(directions))
        supporters = tuple(x.specialist_id for x in items if x.action == action)
        holders = tuple(x.specialist_id for x in items if x.action == "HOLD")
        if holders:
            return ConsensusResult(Decision.WAIT_FOR_CONFIRMATION, None, supporters, holders,
                                   ("One or more specialists withheld confirmation.",))
        return ConsensusResult(Decision.TRADE_CANDIDATE, action, supporters, (),
                               tuple(x.reason for x in items))
