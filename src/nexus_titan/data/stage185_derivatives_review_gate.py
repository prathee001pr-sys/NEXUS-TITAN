"""Stage 185: conservative independent research-only F&O review aggregator.

It NEVER grants broker access, order submission, live trading, capital use,
strategy promotion, or autonomous execution, even when all evidence is green.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .stage180_paper_evidence_gate import PaperEvidenceReceipt
from .stage181_order_lifecycle import OrderLifecycleReceipt
from .stage182_option_legs import OptionLegReceipt
from .stage183_option_stress import OptionStressReceipt
from .stage184_oos_stability import OOSStabilityReceipt


@dataclass(frozen=True, slots=True)
class DerivativesReviewReceipt:
    accepted_for_offline_paper_review: bool
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_derivatives_review(*, prior: PaperEvidenceReceipt,
                                lifecycle: OrderLifecycleReceipt,
                                legs: OptionLegReceipt,
                                stress: OptionStressReceipt,
                                oos: OOSStabilityReceipt,
                                contract_metadata_independently_verified: bool,
                                dataset_sha256: str,
                                dataset_provenance_independently_verified: bool,
                                live_requested: bool = False,
                                promotion_requested: bool = False,
                                autonomous_requested: bool = False) -> DerivativesReviewReceipt:
    checks = {
        'prior paper evidence': isinstance(prior, PaperEvidenceReceipt) and prior.accepted_for_offline_paper_review is True and not prior.blockers and prior.live_trading_authorized is False and prior.strategy_promotion_authorized is False,
        'completed synthetic order': isinstance(lifecycle, OrderLifecycleReceipt) and lifecycle.accepted is True and not lifecycle.blockers and lifecycle.final_state == 'FILLED' and lifecycle.filled_quantity is not None and lifecycle.filled_quantity > 0,
        'F&O leg consistency': isinstance(legs, OptionLegReceipt) and legs.accepted is True and not legs.blockers and legs.leg_count > 0 and bool(legs.legs_sha256),
        'scenario stress': isinstance(stress, OptionStressReceipt) and stress.accepted is True and not stress.blockers and stress.scenario_count > 0 and isinstance(legs, OptionLegReceipt) and stress.legs_sha256 == legs.legs_sha256 and bool(stress.legs_sha256),
        'walk-forward OOS evidence': isinstance(oos, OOSStabilityReceipt) and oos.accepted is True and not oos.blockers and oos.checked_folds >= 2 and isinstance(dataset_sha256, str) and bool(re.fullmatch(r'[0-9a-f]{64}', dataset_sha256)) and oos.dataset_sha256 == dataset_sha256,
        'independently verified contract metadata': contract_metadata_independently_verified is True,
        'independently verified dataset provenance': dataset_provenance_independently_verified is True,
        'live trading prohibited': live_requested is False,
        'promotion prohibited': promotion_requested is False,
        'autonomous execution prohibited': autonomous_requested is False,
    }
    blockers = tuple(k for k, v in checks.items() if not v)
    return DerivativesReviewReceipt(not blockers, blockers, False, False, False)
