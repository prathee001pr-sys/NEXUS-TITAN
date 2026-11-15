import pytest

from nexus_titan.operations.stage143_shadow_reconciliation import (
    PaperOrder,
    PaperFill,
    reconcile_shadow_orders,
)


def test_complete_paper_fill():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [PaperFill("F1", "O1", 10, 100.0)],
    )
    assert result.accepted
    assert result.total_filled_quantity == 10
    assert not result.live_authorized


def test_partial_fills_can_complete_order():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [
            PaperFill("F1", "O1", 4, 100),
            PaperFill("F2", "O1", 6, 101),
        ],
    )
    assert result.accepted


def test_incomplete_fill_blocked():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [PaperFill("F1", "O1", 5, 100)],
    )
    assert "incomplete_fill" in result.reasons


def test_overfill_blocked():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [PaperFill("F1", "O1", 11, 100)],
    )
    assert "overfill" in result.reasons


def test_duplicate_fill_blocked():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [
            PaperFill("F1", "O1", 10, 100),
            PaperFill("F1", "O1", 10, 100),
        ],
    )
    assert "duplicate_fill_id" in result.reasons


def test_unknown_order_blocked():
    result = reconcile_shadow_orders(
        [PaperOrder("O1", 10)],
        [PaperFill("F1", "UNKNOWN", 10, 100)],
    )
    assert "unknown_order_id" in result.reasons


def test_duplicate_order_blocked():
    result = reconcile_shadow_orders(
        [
            PaperOrder("O1", 10),
            PaperOrder("O1", 10),
        ],
        [PaperFill("F1", "O1", 10, 100)],
    )
    assert "duplicate_order_id" in result.reasons


@pytest.mark.parametrize("fill", [
    PaperFill("F1", "O1", 0, 100),
    PaperFill("F1", "O1", 10, -1),
    PaperFill("F1", "O1", 10, float("nan")),
])
def test_invalid_fill_rejected(fill):
    with pytest.raises(ValueError):
        reconcile_shadow_orders(
            [PaperOrder("O1", 10)],
            [fill],
        )
