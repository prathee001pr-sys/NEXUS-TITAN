"""Stage 195: fail-closed, synthetic-only combined research evidence gate.

No result from this module can authorize broker orders, live trading, model
promotion, or autonomous execution. Caller-provided 'verified' flags are
attestations, NOT cryptographic verification of real market data.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from decimal import Decimal

from .stage191_portfolio_replay_ledger import PortfolioReplayLedgerReceipt
from .stage192_equity_drawdown import EquityDrawdownReceipt
from .stage193_cost_stress import ExtraCostStressReceipt
from .stage194_holdout_trade_split import HoldoutTradeSplitReceipt

_HEX = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class OfflinePortfolioEvidenceReceipt:
    accepted_for_synthetic_research_review: bool
    evidence_sha256: str
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_offline_portfolio_gate(*, ledger: PortfolioReplayLedgerReceipt,
                                    equity: EquityDrawdownReceipt,
                                    costs: ExtraCostStressReceipt,
                                    split: HoldoutTradeSplitReceipt,
                                    config_sha256: str,
                                    provenance_attested: bool,
                                    independent_risk_veto_attested: bool,
                                    holdout_separation_attested: bool,
                                    live_requested: bool = False,
                                    autonomous_requested: bool = False,
                                    promotion_requested: bool = False) -> OfflinePortfolioEvidenceReceipt:
    valid_ledger = (isinstance(ledger, PortfolioReplayLedgerReceipt)
                    and ledger.accepted is True and not ledger.blockers
                    and type(ledger.trade_count) is int and ledger.trade_count >= 3
                    and type(ledger.net_pnl) is Decimal and ledger.net_pnl.is_finite()
                    and isinstance(ledger.ledger_sha256, str)
                    and _HEX.fullmatch(ledger.ledger_sha256))
    digest = ledger.ledger_sha256 if valid_ledger else ''
    checks = {
        'valid synthetic replay ledger': bool(valid_ledger),
        'linked closed-equity risk': isinstance(equity, EquityDrawdownReceipt)
            and equity.accepted is True and not equity.blockers
            and equity.ledger_sha256 == digest
            and type(equity.ending_equity) is Decimal and equity.ending_equity.is_finite()
            and type(equity.max_drawdown_bps) is Decimal and equity.max_drawdown_bps.is_finite()
            and bool(equity.equity_sha256)
            and isinstance(equity.equity_sha256, str) and bool(_HEX.fullmatch(equity.equity_sha256)),
        'linked additional-cost scenario': isinstance(costs, ExtraCostStressReceipt)
            and costs.accepted is True and not costs.blockers and costs.ledger_sha256 == digest
            and type(costs.stressed_net_pnl) is Decimal and costs.stressed_net_pnl.is_finite()
            and isinstance(costs.cost_sha256, str) and bool(_HEX.fullmatch(costs.cost_sha256)),
        'linked embargoed holdout': isinstance(split, HoldoutTradeSplitReceipt)
            and split.accepted is True and not split.blockers and split.ledger_sha256 == digest
            and type(split.train_count) is int and type(split.holdout_count) is int
            and split.train_count >= 1 and split.holdout_count >= 2
            and isinstance(split.split_sha256, str) and bool(_HEX.fullmatch(split.split_sha256)),
        'portfolio split reconciles trade count': bool(valid_ledger)
            and isinstance(split, HoldoutTradeSplitReceipt)
            and type(split.train_count) is int and type(split.holdout_count) is int
            and split.train_count + split.holdout_count == ledger.trade_count,
        'portfolio split reconciles net pnl': bool(valid_ledger)
            and isinstance(split, HoldoutTradeSplitReceipt)
            and type(split.train_net_pnl) is Decimal and split.train_net_pnl.is_finite()
            and type(split.holdout_net_pnl) is Decimal and split.holdout_net_pnl.is_finite()
            and split.train_net_pnl + split.holdout_net_pnl == ledger.net_pnl,
        'config fingerprint': isinstance(config_sha256, str) and bool(_HEX.fullmatch(config_sha256)),
        'provenance attestation': provenance_attested is True,
        'independent risk veto attestation': independent_risk_veto_attested is True,
        'holdout separation attestation': holdout_separation_attested is True,
        'live trading prohibited': live_requested is False,
        'autonomous orders prohibited': autonomous_requested is False,
        'strategy promotion prohibited': promotion_requested is False,
    }
    blockers = tuple(k for k, ok in checks.items() if not ok)
    if blockers:
        return OfflinePortfolioEvidenceReceipt(False, '', blockers)
    raw = json.dumps({'ledger': digest, 'equity': equity.equity_sha256,
                      'costs': costs.cost_sha256, 'holdout': split.split_sha256,
                      'config': config_sha256}, sort_keys=True, separators=(',', ':'))
    return OfflinePortfolioEvidenceReceipt(True, hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
