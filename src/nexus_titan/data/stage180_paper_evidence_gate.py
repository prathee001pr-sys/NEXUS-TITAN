"""Stage 180: fail-closed aggregate audit for offline PAPER-RESEARCH review only.

A green receipt CANNOT authorize live orders, autonomous trading, risk override,
capital deployment, model promotion, or broker connectivity.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .stage175_offline_review_gate import OfflineReviewReceipt
from .stage176_quote_sanity import QuoteReceipt
from .stage177_liquidity_participation import LiquidityReceipt
from .stage178_portfolio_risk_budget import PortfolioRiskReceipt
from .stage179_closed_trade_scorecard import ScorecardReceipt

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class PaperEvidenceReceipt:
    accepted_for_offline_paper_review: bool
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_paper_evidence(
    *, prior: OfflineReviewReceipt, quote: QuoteReceipt,
    liquidity: LiquidityReceipt, risk: PortfolioRiskReceipt,
    scorecard: ScorecardReceipt,
    dataset_sha256: str, verified_snapshot_sha256: str,
    cost_assumptions_verified: bool, real_fill_claimed: bool = False,
    live_requested: bool = False, promotion_requested: bool = False,
) -> PaperEvidenceReceipt:
    """Consume explicit, independently verified read-only evidence receipts."""
    checks = {
        'prior offline review': isinstance(prior, OfflineReviewReceipt) and prior.accepted_for_offline_review is True and not prior.blockers and prior.live_trading_authorized is False,
        'quote sanity': isinstance(quote, QuoteReceipt) and quote.accepted is True and not quote.blockers,
        'liquidity': isinstance(liquidity, LiquidityReceipt) and liquidity.accepted is True and not liquidity.blockers,
        'portfolio risk': isinstance(risk, PortfolioRiskReceipt) and risk.accepted is True and not risk.blockers,
        'closed trade scorecard': isinstance(scorecard, ScorecardReceipt) and scorecard.accepted is True and not scorecard.blockers,
        'verified dataset digest': (
            isinstance(dataset_sha256, str) and bool(_DIGEST.fullmatch(dataset_sha256))
            and isinstance(verified_snapshot_sha256, str) and bool(_DIGEST.fullmatch(verified_snapshot_sha256))
            and dataset_sha256 == verified_snapshot_sha256
        ),
        'calibrated cost assumptions': cost_assumptions_verified is True,
        'no real fill claim': real_fill_claimed is False,
        'live trading prohibited': live_requested is False,
        'promotion prohibited': promotion_requested is False,
    }
    blockers = tuple(name for name, success in checks.items() if not success)
    return PaperEvidenceReceipt(not blockers, blockers, False, False)
