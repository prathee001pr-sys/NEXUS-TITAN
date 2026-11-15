from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class BacktestExecution:
    gross_pnl: float
    brokerage: float
    taxes_fees: float
    spread_cost: float
    slippage_cost: float
    reported_net_pnl: float


@dataclass(frozen=True)
class BacktestValidation:
    accepted: bool
    calculated_net_pnl: float
    total_costs: float
    reasons: tuple[str, ...]
    live_authorized: bool = False


def validate_backtest_execution(
    execution: BacktestExecution,
    *,
    tolerance: float = 0.01,
) -> BacktestValidation:
    if not isinstance(execution, BacktestExecution):
        raise TypeError("BacktestExecution required")

    if (
        type(tolerance) not in (int, float)
        or not isfinite(tolerance)
        or tolerance < 0
    ):
        raise ValueError("Invalid tolerance")

    fields = (
        execution.gross_pnl,
        execution.brokerage,
        execution.taxes_fees,
        execution.spread_cost,
        execution.slippage_cost,
        execution.reported_net_pnl,
    )

    if any(
        type(value) not in (int, float)
        or not isfinite(value)
        for value in fields
    ):
        raise ValueError("Invalid financial value")

    costs = (
        execution.brokerage
        + execution.taxes_fees
        + execution.spread_cost
        + execution.slippage_cost
    )

    if not isfinite(costs):
        raise ValueError("Cost overflow")

    if any(
        value < 0
        for value in (
            execution.brokerage,
            execution.taxes_fees,
            execution.spread_cost,
            execution.slippage_cost,
        )
    ):
        raise ValueError("Negative execution cost")

    net = execution.gross_pnl - costs

    if not isfinite(net):
        raise ValueError("Net P&L overflow")

    reasons = []

    if abs(net - execution.reported_net_pnl) > tolerance:
        reasons.append("net_pnl_mismatch")

    if costs == 0:
        reasons.append("zero_execution_costs_require_review")

    return BacktestValidation(
        accepted=not reasons,
        calculated_net_pnl=float(net),
        total_costs=float(costs),
        reasons=tuple(reasons),
        live_authorized=False,
    )
