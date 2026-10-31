"""Supervised AI multi-agent intelligence and deterministic veto framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from nexus_titan.research.indicators import atr, sma
from nexus_titan.risk.portfolio_risk import InstrumentSpec, PortfolioRiskManager, PreTradeRiskResult


@dataclass(frozen=True)
class AgentAssessment:
    agent_id: str
    decision: str
    confidence: float
    evidence: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MarketAnalystAgent:
    """Analyze market regime, trend, and volatility from supplied candles."""

    def analyze(self, candles: list[dict[str, float]]) -> AgentAssessment:
        if len(candles) < 20:
            return AgentAssessment("MARKET_ANALYST", "HOLD", 0.5,
                                   "Insufficient candles (<20) to classify market regime.")
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        sma20 = sma(closes, 20)[-1]
        atr14 = atr(highs, lows, closes, 14)[-1]
        current_close = closes[-1]
        if sma20 is None or atr14 is None:
            return AgentAssessment("MARKET_ANALYST", "HOLD", 0.5,
                                   "Indicator calculation returned None.")
        volatility_pct = (atr14 / current_close) * 100
        is_uptrend = current_close > sma20
        regime = "BULL_TREND" if is_uptrend else "BEAR_TREND"
        regime += "_HIGH_VOL" if volatility_pct > 1.5 else "_NORMAL_VOL"
        decision = "BUY" if is_uptrend else "SELL"
        confidence = min(0.9, 0.6 + (0.1 if volatility_pct < 2.0 else 0.0))
        return AgentAssessment(
            "MARKET_ANALYST", decision, confidence,
            f"Regime: {regime} | Close: {current_close:.2f} vs SMA20: {sma20:.2f} | ATR%: {volatility_pct:.2f}%",
        )


class DeterministicRiskVetoAgent:
    """Authoritative deterministic veto agent. An LLM cannot override this veto."""

    def __init__(self, risk_manager: PortfolioRiskManager | None = None):
        self.risk_manager = risk_manager or PortfolioRiskManager()

    def evaluate(
        self, capital: float, current_exposure: float, open_positions: int,
        daily_loss_pct: float, consecutive_losses: int, entry_price: float,
        stop_price: float, spec: InstrumentSpec | None = None,
    ) -> tuple[AgentAssessment, PreTradeRiskResult]:
        result = self.risk_manager.evaluate_order(
            capital=capital, current_exposure=current_exposure,
            current_open_positions=open_positions,
            realized_daily_loss_pct=daily_loss_pct, consecutive_losses=consecutive_losses,
            entry_price=entry_price, stop_price=stop_price, spec=spec,
        )
        assessment = AgentAssessment(
            "DETERMINISTIC_RISK_VETO", "BUY" if result.approved else "VETO", 1.0,
            f"Veto status: {not result.approved} | Reason: {result.reason}",
        )
        return assessment, result


class MarketDigitalTwin:
    """Replayable market-state model for deterministic scenario and stress testing."""

    def run_stress_test(self, base_candles: list[dict[str, float]],
                        scenario: str = "FLASH_CRASH") -> list[dict[str, float]]:
        stressed = [dict(c) for c in base_candles]
        if not stressed:
            return stressed
        last = stressed[-1]
        if scenario == "FLASH_CRASH":
            crash_open = last["close"] * 0.95
            stressed.append({
                "timestamp": "STRESS_TICK_1", "open": crash_open,
                "high": last["close"], "low": crash_open * 0.97,
                "close": crash_open * 0.98, "volume": last["volume"] * 4.0,
            })
        elif scenario == "VOLATILITY_SPIKE":
            stressed.append({
                "timestamp": "STRESS_TICK_VOL", "open": last["close"],
                "high": last["close"] * 1.04, "low": last["close"] * 0.96,
                "close": last["close"] * 1.01, "volume": last["volume"] * 3.0,
            })
        else:
            raise ValueError(f"Unsupported stress scenario: {scenario}")
        return stressed


class MetaAgentCoordinator:
    """Supervised meta-agent orchestration with an immutable deterministic risk veto."""

    def __init__(self):
        self.analyst = MarketAnalystAgent()
        self.veto_agent = DeterministicRiskVetoAgent()
        self.digital_twin = MarketDigitalTwin()

    def process_cycle(
        self, candles: list[dict[str, float]], capital: float,
        current_exposure: float, open_positions: int, daily_loss_pct: float,
        consecutive_losses: int, stop_price: float,
        spec: InstrumentSpec | None = None,
    ) -> dict[str, Any]:
        market_assessment = self.analyst.analyze(candles)
        if market_assessment.decision != "BUY":
            return {
                "action": "HOLD",
                "reason": f"Analyst proposed {market_assessment.decision}: {market_assessment.evidence}",
                "vetoed": False, "analyst_assessment": market_assessment,
            }
        entry_price = candles[-1]["close"]
        veto_assessment, risk_result = self.veto_agent.evaluate(
            capital=capital, current_exposure=current_exposure, open_positions=open_positions,
            daily_loss_pct=daily_loss_pct, consecutive_losses=consecutive_losses,
            entry_price=entry_price, stop_price=stop_price, spec=spec,
        )
        if not risk_result.approved:
            return {
                "action": "VETO", "reason": f"Trade blocked by Risk Veto: {risk_result.reason}",
                "vetoed": True, "risk_result": risk_result,
                "analyst_assessment": market_assessment, "veto_assessment": veto_assessment,
            }
        return {
            "action": "BUY", "quantity": risk_result.quantity,
            "entry_price": risk_result.effective_entry, "stop_price": risk_result.effective_stop,
            "risk_amount": risk_result.risk_amount,
            "reason": "All agent checks passed and trade approved by Risk Veto.",
            "vetoed": False, "risk_result": risk_result,
            "analyst_assessment": market_assessment,
        }
