"""Integrated research-to-risk decision pipeline; never submits orders."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from .consensus import ConsensusEngine, ConsensusResult, Decision, SignalProposal
from .market_state import MarketState


class PipelineStatus(StrEnum):
    DATA_INVALID = "DATA INVALID"
    NO_TRADE = "NO TRADE"
    WAIT_FOR_CONFIRMATION = "WAIT FOR CONFIRMATION"
    RISK_CHECK_REQUIRED = "RISK CHECK REQUIRED"
    RISK_REJECTED = "RISK REJECTED"
    SHADOW_CANDIDATE = "SHADOW CANDIDATE"


@dataclass(frozen=True, slots=True)
class RiskRequest:
    """Explicit pre-trade risk inputs. No defaults for capital or protective stop."""
    capital: float
    entry_price: float
    stop_price: float
    symbol: str
    side: str
    lot_size: int
    tick_size: float = 0.05
    current_exposure: float = 0.0
    current_open_positions: int = 0
    realized_daily_loss_pct: float = 0.0
    consecutive_losses: int = 0
    slippage_buffer: float = 0.0
    current_drawdown_pct: float = 0.0


@dataclass(frozen=True, slots=True)
class PipelineResult:
    status: PipelineStatus
    consensus: ConsensusResult
    risk_approved: bool | None
    risk_quantity: int
    risk_reason: str
    order_submitted: bool = False


class TradingIntelligencePipeline:
    """Connect T01-T04 state evidence, T05 proposals, T06 consensus and risk veto.

    A passing result is only a shadow/research candidate. This class has no broker
    dependency and deliberately cannot submit, route, or enable a live order.
    """

    def __init__(self, consensus: ConsensusEngine | None = None,
                 risk_engine: AuthoritativeRiskEngine | None = None) -> None:
        self.consensus = consensus or ConsensusEngine()
        self.risk_engine = risk_engine or AuthoritativeRiskEngine()

    def evaluate(self, state: MarketState, proposals: Iterable[SignalProposal],
                 risk_request: RiskRequest | None = None) -> PipelineResult:
        consensus = self.consensus.evaluate(state, proposals)
        if consensus.decision is Decision.DATA_INVALID:
            return PipelineResult(PipelineStatus.DATA_INVALID, consensus, None, 0,
                                  "Market-state quality gate failed.")
        if consensus.decision is Decision.NO_TRADE:
            return PipelineResult(PipelineStatus.NO_TRADE, consensus, None, 0,
                                  "Consensus produced no directional trade candidate.")
        if consensus.decision is Decision.WAIT_FOR_CONFIRMATION:
            return PipelineResult(PipelineStatus.WAIT_FOR_CONFIRMATION, consensus, None, 0,
                                  "Specialist evidence is incomplete or conflicting.")
        if risk_request is None:
            return PipelineResult(PipelineStatus.RISK_CHECK_REQUIRED, consensus, None, 0,
                                  "A candidate cannot proceed without explicit independent risk inputs.")
        if (consensus.action not in {"BUY", "SELL"} or not isinstance(risk_request.side, str)
                or risk_request.side.upper() != consensus.action):
            return PipelineResult(PipelineStatus.RISK_REJECTED, consensus, False, 0,
                                  "Risk side must match the consensus direction.")
        risk = self.risk_engine.size_and_validate(
            capital=risk_request.capital,
            entry_price=risk_request.entry_price,
            stop_price=risk_request.stop_price,
            symbol=risk_request.symbol,
            lot_size=risk_request.lot_size,
            tick_size=risk_request.tick_size,
            current_exposure=risk_request.current_exposure,
            current_open_positions=risk_request.current_open_positions,
            realized_daily_loss_pct=risk_request.realized_daily_loss_pct,
            consecutive_losses=risk_request.consecutive_losses,
            slippage_buffer=risk_request.slippage_buffer,
            current_drawdown_pct=risk_request.current_drawdown_pct,
            side=risk_request.side.upper(),
        )
        if not risk.approved or risk.quantity <= 0:
            return PipelineResult(PipelineStatus.RISK_REJECTED, consensus, False, 0, risk.reason)
        return PipelineResult(PipelineStatus.SHADOW_CANDIDATE, consensus, True, risk.quantity,
                              risk.reason + " No order was submitted.")
