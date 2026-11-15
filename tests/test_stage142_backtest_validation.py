import pytest

from nexus_titan.operations.stage142_backtest_validation import (
    BacktestExecution,
    validate_backtest_execution,
)


def sample(**changes):
    values = dict(
        gross_pnl=1000.0,
        brokerage=40.0,
        taxes_fees=20.0,
        spread_cost=15.0,
        slippage_cost=25.0,
        reported_net_pnl=900.0,
    )
    values.update(changes)
    return BacktestExecution(**values)


def test_valid_cost_adjusted_backtest():
    result = validate_backtest_execution(sample())
    assert result.accepted
    assert result.total_costs == 100
    assert result.calculated_net_pnl == 900
    assert not result.live_authorized


def test_mismatched_net_pnl_blocked():
    result = validate_backtest_execution(
        sample(reported_net_pnl=950)
    )
    assert not result.accepted
    assert "net_pnl_mismatch" in result.reasons


def test_zero_costs_require_review():
    result = validate_backtest_execution(sample(
        brokerage=0,
        taxes_fees=0,
        spread_cost=0,
        slippage_cost=0,
        reported_net_pnl=1000,
    ))
    assert not result.accepted


@pytest.mark.parametrize("changes", [
    {"brokerage": -1},
    {"slippage_cost": -2},
    {"gross_pnl": float("nan")},
    {"taxes_fees": float("inf")},
])
def test_invalid_values_rejected(changes):
    with pytest.raises(ValueError):
        validate_backtest_execution(sample(**changes))


def test_invalid_tolerance_rejected():
    with pytest.raises(ValueError):
        validate_backtest_execution(
            sample(), tolerance=-1
        )


def test_invalid_type_rejected():
    with pytest.raises(TypeError):
        validate_backtest_execution(None)
