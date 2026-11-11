from datetime import datetime, timezone

import pytest

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


def valid_reports():
    historical = review_historical_bars(
        [
            HistoricalBar(
                timestamp=datetime(
                    2026, 1, 1, 9, 15,
                    tzinfo=timezone.utc,
                ),
                open=100,
                high=105,
                low=95,
                close=102,
                volume=100,
            )
        ],
        source="synthetic_test",
    )

    backtest = validate_backtest_execution(
        BacktestExecution(
            gross_pnl=1000,
            brokerage=40,
            taxes_fees=20,
            spread_cost=15,
            slippage_cost=25,
            reported_net_pnl=900,
        )
    )

    shadow = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [PaperFill("F1", "O1", 10, 100)],
    )

    return historical, backtest, shadow


def test_all_gates_allow_human_review_only():
    result = evaluate_research_acceptance(
        *valid_reports()
    )
    assert result.accepted_for_review
    assert result.status == "HUMAN_REVIEW"
    assert result.human_review_required
    assert not result.promotion_authorized
    assert not result.live_authorized


def test_historical_failure_blocks():
    h, b, s = valid_reports()
    from dataclasses import replace
    h = replace(
        h,
        accepted=False,
        reasons=("duplicate_timestamp",),
    )
    result = evaluate_research_acceptance(h, b, s)
    assert not result.accepted_for_review
    assert "historical_integrity_failed" in result.reasons


def test_backtest_failure_blocks():
    h, b, s = valid_reports()
    from dataclasses import replace
    b = replace(
        b,
        accepted=False,
        reasons=("net_pnl_mismatch",),
    )
    result = evaluate_research_acceptance(h, b, s)
    assert not result.accepted_for_review


def test_shadow_failure_blocks():
    h, b, s = valid_reports()
    from dataclasses import replace
    s = replace(
        s,
        accepted=False,
        reasons=("overfill",),
    )
    result = evaluate_research_acceptance(h, b, s)
    assert not result.accepted_for_review


def test_empty_shadow_evidence_blocks():
    h, b, s = valid_reports()
    from dataclasses import replace
    s = replace(
        s,
        order_count=0,
        fill_count=0,
    )
    result = evaluate_research_acceptance(h, b, s)
    assert not result.accepted_for_review


def test_live_authorization_rejected():
    h, b, s = valid_reports()
    from dataclasses import replace
    b = replace(b, live_authorized=True)
    with pytest.raises(ValueError):
        evaluate_research_acceptance(h, b, s)


def test_invalid_input_rejected():
    with pytest.raises(TypeError):
        evaluate_research_acceptance(
            None, None, None
        )
