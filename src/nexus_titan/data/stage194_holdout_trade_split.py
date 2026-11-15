"""Stage 194: closed-trade train/holdout separation and calendar embargo.

Checks only *declared* close times. Does not prove model training did not see
holdout data, and does not independently verify market provenance.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from .stage191_portfolio_replay_ledger import (
    ClosedReplay, PortfolioReplayLedgerReceipt, audit_portfolio_replay_ledger, _as_utc,
)


@dataclass(frozen=True, slots=True)
class HoldoutTradeSplitReceipt:
    accepted: bool
    ledger_sha256: str
    train_count: int
    holdout_count: int
    train_net_pnl: Decimal | None
    holdout_net_pnl: Decimal | None
    split_sha256: str
    blockers: tuple[str, ...]


def audit_holdout_trade_split(trades: tuple[ClosedReplay, ...], *, ledger: PortfolioReplayLedgerReceipt,
                              train_end: datetime, holdout_start: datetime,
                              embargo_days: int = 1, min_holdout_trades: int = 2) -> HoldoutTradeSplitReceipt:
    errors: list[str] = []
    checked = audit_portfolio_replay_ledger(trades)
    if not isinstance(ledger, PortfolioReplayLedgerReceipt) or not checked.accepted or checked != ledger:
        errors.append('replay ledger mismatch')
    if type(embargo_days) is not int or not 1 <= embargo_days <= 365:
        errors.append('invalid embargo days')
    if type(min_holdout_trades) is not int or not 2 <= min_holdout_trades <= 5000:
        errors.append('invalid minimum holdout trades')
    try:
        end = _as_utc(train_end)
        begin = _as_utc(holdout_start)
        if begin <= end or (type(embargo_days) is int and begin - end < timedelta(days=embargo_days)):
            errors.append('holdout overlaps or violates embargo')
    except (ValueError, TypeError, OverflowError):
        errors.append('invalid time boundaries')
        end = begin = None
    if errors:
        return HoldoutTradeSplitReceipt(False, '', 0, 0, None, None, '', tuple(errors))
    train = []
    holdout = []
    for i, trade in enumerate(trades):
        t = trade.closed_at.astimezone(timezone.utc)
        if t <= end:
            train.append(trade)
        elif t >= begin:
            holdout.append(trade)
        else:
            errors.append(f'trade {i}: closure inside embargo')
    if not train:
        errors.append('no training-period closed trades')
    if len(holdout) < min_holdout_trades:
        errors.append('insufficient holdout closed trades')
    if errors:
        return HoldoutTradeSplitReceipt(False, ledger.ledger_sha256, len(train), len(holdout),
                                        None, None, '', tuple(errors))
    train_net = sum((x.receipt.net_pnl for x in train), Decimal(0))
    holdout_net = sum((x.receipt.net_pnl for x in holdout), Decimal(0))
    raw = json.dumps({'ledger': ledger.ledger_sha256, 'train_end': end.isoformat(),
                      'holdout_start': begin.isoformat(), 'embargo_days': embargo_days,
                      'train_ids': [x.trade_id for x in train],
                      'holdout_ids': [x.trade_id for x in holdout]}, sort_keys=True,
                     separators=(',', ':'))
    return HoldoutTradeSplitReceipt(True, ledger.ledger_sha256, len(train), len(holdout),
                                    train_net, holdout_net,
                                    hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
