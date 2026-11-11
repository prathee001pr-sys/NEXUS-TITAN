from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class PerformanceAttribution:
    trade_count: int
    net_pnl: float
    gross_pnl: float
    total_costs: float
    win_rate: float
    max_drawdown: float


def attribute_closed_trades(trades):
    if not isinstance(trades, (list, tuple)) or not trades:
        raise ValueError("Nonempty trade list required")

    gross = 0.0
    costs = 0.0
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    wins = 0

    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("Invalid trade")
        if set(trade) != {"gross_pnl", "costs", "closed"}:
            raise ValueError("Unexpected trade fields")
        if trade["closed"] is not True:
            raise ValueError("Only closed trades allowed")

        g = trade["gross_pnl"]
        c = trade["costs"]

        if (
            isinstance(g, bool)
            or isinstance(c, bool)
            or not isinstance(g, (int, float))
            or not isinstance(c, (int, float))
            or not isfinite(g)
            or not isfinite(c)
            or c < 0
        ):
            raise ValueError("Invalid financial values")

        net = float(g - c)
        gross += g
        costs += c
        equity += net
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        wins += net > 0

    return PerformanceAttribution(
        trade_count=len(trades),
        net_pnl=gross - costs,
        gross_pnl=float(gross),
        total_costs=float(costs),
        win_rate=wins / len(trades),
        max_drawdown=float(drawdown),
    )
