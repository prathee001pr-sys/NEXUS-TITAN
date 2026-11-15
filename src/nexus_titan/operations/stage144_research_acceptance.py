from dataclasses import dataclass

from nexus_titan.operations.stage141_historical_integrity import (
    IntegrityReport,
)
from nexus_titan.operations.stage142_backtest_validation import (
    BacktestValidation,
)
from nexus_titan.operations.stage143_shadow_reconciliation import (
    ReconciliationReport,
)


@dataclass(frozen=True)
class ResearchAcceptance:
    accepted_for_review: bool
    status: str
    reasons: tuple[str, ...]
    human_review_required: bool = True
    promotion_authorized: bool = False
    live_authorized: bool = False


def evaluate_research_acceptance(
    historical: IntegrityReport,
    backtest: BacktestValidation,
    shadow: ReconciliationReport,
) -> ResearchAcceptance:

    if not isinstance(historical, IntegrityReport):
        raise TypeError("IntegrityReport required")

    if not isinstance(backtest, BacktestValidation):
        raise TypeError("BacktestValidation required")

    if not isinstance(shadow, ReconciliationReport):
        raise TypeError("ReconciliationReport required")

    for report in (historical, backtest, shadow):
        if (
            type(report.accepted) is not bool
            or type(report.live_authorized) is not bool
            or not isinstance(report.reasons, tuple)
            or any(type(r) is not str for r in report.reasons)
        ):
            raise ValueError("Invalid gate report")

        if report.live_authorized:
            raise ValueError("Live authorization prohibited")

    if (
        type(historical.research_authorized) is not bool
        or type(historical.bar_count) is not int
        or historical.bar_count < 1
        or type(shadow.order_count) is not int
        or type(shadow.fill_count) is not int
        or type(shadow.total_filled_quantity) is not int
        or shadow.order_count < 0
        or shadow.fill_count < 0
        or shadow.total_filled_quantity < 0
    ):
        raise ValueError("Invalid gate metadata")

    reasons = []

    if not historical.accepted or historical.reasons:
        reasons.append("historical_integrity_failed")
        reasons.extend(historical.reasons)

    if not backtest.accepted or backtest.reasons:
        reasons.append("backtest_validation_failed")
        reasons.extend(backtest.reasons)

    if not shadow.accepted or shadow.reasons:
        reasons.append("shadow_reconciliation_failed")
        reasons.extend(shadow.reasons)

    if historical.research_authorized:
        reasons.append("unexpected_research_authorization")

    if shadow.order_count == 0 or shadow.fill_count == 0:
        reasons.append("missing_shadow_execution_evidence")

    unique_reasons = tuple(dict.fromkeys(reasons))

    return ResearchAcceptance(
        accepted_for_review=not unique_reasons,
        status=(
            "HUMAN_REVIEW"
            if not unique_reasons
            else "BLOCKED"
        ),
        reasons=unique_reasons,
        human_review_required=True,
        promotion_authorized=False,
        live_authorized=False,
    )
