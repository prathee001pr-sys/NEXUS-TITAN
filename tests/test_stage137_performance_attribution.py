import pytest

from nexus_titan.operations.stage137_performance_attribution import (
    attribute_closed_trades,
)


def test_closed_trade_attribution():
    result = attribute_closed_trades([
        {"gross_pnl": 100, "costs": 10, "closed": True},
        {"gross_pnl": -50, "costs": 5, "closed": True},
    ])
    assert result.trade_count == 2
    assert result.net_pnl == 35
    assert result.total_costs == 15
    assert result.win_rate == 0.5
    assert result.max_drawdown == 55


@pytest.mark.parametrize("trades", [
    [],
    [{"gross_pnl": 1, "costs": 0, "closed": False}],
    [{"gross_pnl": float("nan"), "costs": 0, "closed": True}],
    [{"gross_pnl": 1, "costs": -1, "closed": True}],
    [{"gross_pnl": 1, "costs": 0, "closed": True, "extra": 1}],
])
def test_invalid_trades_rejected(trades):
    with pytest.raises(ValueError):
        attribute_closed_trades(trades)
