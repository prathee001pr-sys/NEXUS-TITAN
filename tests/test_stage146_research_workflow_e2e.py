from datetime import datetime, timezone

from nexus_titan.operations.stage141_historical_integrity import (
    HistoricalBar,
    review_historical_bars,
)
from nexus_titan.operations.stage142_backtest_validation import (
    BacktestExecution,
    validate_backtest_execution,
)
from nexus_titan.operations.stage143_shadow_reconciliation import (
    PaperOrder,
    PaperFill,
    reconcile_shadow_orders,
)
from nexus_titan.operations.stage144_research_acceptance import (
    evaluate_research_acceptance,
)
from nexus_titan.operations.stage145_dashboard_status import (
    build_dashboard_research_status,
)


def run_workflow(
    *,
    bad_data=False,
    bad_pnl=False,
    bad_fill=False,
):
    historical = review_historical_bars(
        [
            HistoricalBar(
                datetime(
                    2026, 1, 1, 9, 15,
                    tzinfo=timezone.utc,
                ),
                100,
                99 if bad_data else 105,
                95,
                102,
                100,
            )
        ],
        source="synthetic_e2e",
    )

    backtest = validate_backtest_execution(
        BacktestExecution(
            gross_pnl=1000,
            brokerage=40,
            taxes_fees=20,
            spread_cost=15,
            slippage_cost=25,
            reported_net_pnl=950 if bad_pnl else 900,
        )
    )

    shadow = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [
            PaperFill(
                "F1",
                "O1",
                11 if bad_fill else 10,
                100,
            )
        ],
    )

    acceptance = evaluate_research_acceptance(
        historical,
        backtest,
        shadow,
    )

    return build_dashboard_research_status(
        "INDIAN_FO",
        acceptance,
    )


def test_complete_research_workflow():
    result = run_workflow()
    assert result.research_status == "HUMAN_REVIEW"
    assert result.research_review_eligible
    assert result.human_review_required
    assert not result.live_trading_enabled
    assert not result.automatic_promotion_enabled


def test_invalid_data_blocks_dashboard():
    result = run_workflow(bad_data=True)
    assert result.research_status == "BLOCKED"
    assert "historical_integrity_failed" in result.reasons


def test_backtest_mismatch_blocks_dashboard():
    result = run_workflow(bad_pnl=True)
    assert result.research_status == "BLOCKED"
    assert "backtest_validation_failed" in result.reasons


def test_shadow_overfill_blocks_dashboard():
    result = run_workflow(bad_fill=True)
    assert result.research_status == "BLOCKED"
    assert "shadow_reconciliation_failed" in result.reasons


def test_multiple_failures_are_reported():
    result = run_workflow(
        bad_data=True,
        bad_pnl=True,
        bad_fill=True,
    )
    assert result.research_status == "BLOCKED"
    assert len(result.reasons) >= 3


def test_repeated_workflow_is_deterministic():
    first = run_workflow()
    second = run_workflow()
    assert first == second
