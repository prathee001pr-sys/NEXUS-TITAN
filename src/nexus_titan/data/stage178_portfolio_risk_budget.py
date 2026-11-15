"""Stage 178: offline capital, notional, initial margin and stop-risk budget audit.

No inferred exchange/broker margins, order sizing, or trading permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class PortfolioRiskReceipt:
    accepted: bool
    risk_bps: Decimal | None
    blockers: tuple[str, ...]


def audit_portfolio_risk(
    *, equity: str, position_notional: str, initial_margin: str,
    risk_at_stop: str, max_leverage: int, max_risk_bps: int,
    margin_verified: bool, stop_model_verified: bool,
) -> PortfolioRiskReceipt:
    """Bound one proposed *synthetic* position against supplied policy limits."""
    blockers: list[str] = []
    if type(max_leverage) is not int or not 1 <= max_leverage <= 100:
        blockers.append('invalid leverage limit')
    if type(max_risk_bps) is not int or not 1 <= max_risk_bps <= 10_000:
        blockers.append('invalid stop risk limit')
    if margin_verified is not True:
        blockers.append('margin assumptions not verified')
    if stop_model_verified is not True:
        blockers.append('stop model not verified')
    risk_bps = None
    try:
        eq, notion, margin, stop_risk = (parse_amount(x) for x in (
            equity, position_notional, initial_margin, risk_at_stop))
        if eq <= 0 or notion <= 0 or margin <= 0 or stop_risk <= 0:
            blockers.append('invalid equity, notional, margin or stop risk')
        else:
            risk_bps = stop_risk * Decimal(10_000) / eq
            if margin > eq:
                blockers.append('insufficient capital for initial margin')
            if type(max_leverage) is int and notion > eq * max_leverage:
                blockers.append('notional exceeds leverage limit')
            if type(max_risk_bps) is int and risk_bps > max_risk_bps:
                blockers.append('stop risk exceeds budget')
    except (ValueError, InvalidOperation, ZeroDivisionError):
        blockers.append('invalid numeric amounts')
    return PortfolioRiskReceipt(not blockers, risk_bps, tuple(blockers))
