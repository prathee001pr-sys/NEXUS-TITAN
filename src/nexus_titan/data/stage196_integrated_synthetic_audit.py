"""Stage 196: true Stage 191 -> 195 offline synthetic portfolio orchestration.

Input trade receipts are caller-supplied: this does not independently authenticate
market data or authorize broker execution. Only previous-stage functions decide
whether supplied synthetic evidence passes their checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from .stage192_equity_drawdown import audit_equity_drawdown
from .stage193_cost_stress import audit_extra_cost_stress
from .stage194_holdout_trade_split import audit_holdout_trade_split
from .stage195_offline_portfolio_gate import evaluate_offline_portfolio_gate


@dataclass(frozen=True, slots=True)
class SyntheticAuditPolicy:
    opening_equity: str
    max_drawdown_bps: int
    extra_cost_per_roundtrip: str
    max_acceptable_loss: str
    train_end: datetime
    holdout_start: datetime
    config_sha256: str
    embargo_days: int = 1
    min_holdout_trades: int = 2


@dataclass(frozen=True, slots=True)
class IntegratedSyntheticReceipt:
    accepted_for_synthetic_review: bool
    evidence_sha256: str
    ledger_sha256: str
    equity_sha256: str
    cost_sha256: str
    holdout_sha256: str
    trade_count: int
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def audit_integrated_synthetic_portfolio(
    trades: tuple[ClosedReplay, ...], *, policy: SyntheticAuditPolicy,
    provenance_attested: bool, independent_risk_veto_attested: bool,
    holdout_separation_attested: bool, live_requested: bool = False,
    autonomous_requested: bool = False, promotion_requested: bool = False,
) -> IntegratedSyntheticReceipt:
    """Recompute each historical stage; no shortcuts or forged accepted flags."""
    if type(policy) is not SyntheticAuditPolicy:
        return IntegratedSyntheticReceipt(False, '', '', '', '', '', 0, ('invalid policy',))
    if live_requested is not False or autonomous_requested is not False or promotion_requested is not False:
        return IntegratedSyntheticReceipt(False, '', '', '', '', '', 0, ('live, autonomous or promotion request prohibited',))
    try:
        ledger = audit_portfolio_replay_ledger(trades)
        if not ledger.accepted:
            return IntegratedSyntheticReceipt(False, '', '', '', '', '', ledger.trade_count,
                                              ('Stage 191: ' + '; '.join(ledger.blockers),))
        equity = audit_equity_drawdown(trades, ledger=ledger,
                                      opening_equity=policy.opening_equity,
                                      max_drawdown_bps=policy.max_drawdown_bps)
        costs = audit_extra_cost_stress(trades, ledger=ledger,
                                        extra_cost_per_roundtrip=policy.extra_cost_per_roundtrip,
                                        max_acceptable_loss=policy.max_acceptable_loss)
        split = audit_holdout_trade_split(trades, ledger=ledger,
                                          train_end=policy.train_end,
                                          holdout_start=policy.holdout_start,
                                          embargo_days=policy.embargo_days,
                                          min_holdout_trades=policy.min_holdout_trades)
        gate = evaluate_offline_portfolio_gate(
            ledger=ledger, equity=equity, costs=costs, split=split,
            config_sha256=policy.config_sha256,
            provenance_attested=provenance_attested,
            independent_risk_veto_attested=independent_risk_veto_attested,
            holdout_separation_attested=holdout_separation_attested,
            live_requested=live_requested, autonomous_requested=autonomous_requested,
            promotion_requested=promotion_requested,
        )
        blockers = tuple(f'Stage 192: {s}' for s in equity.blockers) + tuple(
            f'Stage 193: {s}' for s in costs.blockers) + tuple(
            f'Stage 194: {s}' for s in split.blockers) + tuple(
            f'Stage 195: {s}' for s in gate.blockers)
        return IntegratedSyntheticReceipt(
            gate.accepted_for_synthetic_research_review is True and not blockers,
            gate.evidence_sha256 if not blockers else '',
            ledger.ledger_sha256, equity.equity_sha256, costs.cost_sha256,
            split.split_sha256, ledger.trade_count, blockers,
        )
    except (ValueError, TypeError, OverflowError, ArithmeticError, AttributeError) as exc:
        # Any malformed input fails closed and cannot produce a trusted digest.
        return IntegratedSyntheticReceipt(False, '', '', '', '', '', 0,
                                          (f'malformed synthetic input: {type(exc).__name__}',))
