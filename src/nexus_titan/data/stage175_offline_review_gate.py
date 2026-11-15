"""Stage 175: strictly offline review gate aggregating independent receipts.

Never grants live order, deployment, capital, strategy-promotion or autonomous
trading permission. All inputs are research evidence, not a broker authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from .stage170_backtest_evidence_gate import EvidenceReceipt
from .stage171_execution_timing import TimingReceipt
from .stage172_replay_integrity import ReplayReceipt
from .stage173_settlement_ledger import SettlementReceipt
from .stage174_walkforward_purge import WalkForwardReceipt


@dataclass(frozen=True, slots=True)
class OfflineReviewReceipt:
    accepted_for_offline_review: bool
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False


def evaluate_offline_review(
    *, evidence: EvidenceReceipt, timing: TimingReceipt,
    replay: ReplayReceipt, settlement: SettlementReceipt,
    walkforward: WalkForwardReceipt, dataset_provenance_verified: bool,
    configuration_frozen: bool, live_requested: bool = False,
) -> OfflineReviewReceipt:
    checks = {
        'prior backtest evidence': isinstance(evidence, EvidenceReceipt) and evidence.accepted_for_offline_review,
        'execution timing': isinstance(timing, TimingReceipt) and timing.accepted,
        'replay integrity': isinstance(replay, ReplayReceipt) and replay.accepted,
        'closed settlement': isinstance(settlement, SettlementReceipt) and settlement.accepted,
        'walkforward purge': isinstance(walkforward, WalkForwardReceipt) and walkforward.accepted,
        'dataset provenance': dataset_provenance_verified is True,
        'frozen configuration': configuration_frozen is True,
        'live trading prohibited': live_requested is False,
    }
    blockers = tuple(name for name, ok in checks.items() if not ok)
    return OfflineReviewReceipt(not blockers, blockers, live_trading_authorized=False)
