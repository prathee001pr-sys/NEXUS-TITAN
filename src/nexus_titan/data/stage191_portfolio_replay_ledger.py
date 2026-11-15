"""Stage 191: bounded chronological ledger of *synthetic* Stage 190 replay receipts.

These receipts can be constructed by callers. This module does not authenticate their
origin or certify market data; independent source checks remain necessary.
Read-only, offline, no broker integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from .stage190_e2e_paper_replay import E2EPaperReplayReceipt

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


@dataclass(frozen=True, slots=True)
class ClosedReplay:
    trade_id: str
    closed_at: datetime
    receipt: E2EPaperReplayReceipt


@dataclass(frozen=True, slots=True)
class PortfolioReplayLedgerReceipt:
    accepted: bool
    trade_count: int
    net_pnl: Decimal | None
    ledger_sha256: str
    blockers: tuple[str, ...]


def _as_utc(stamp: datetime) -> datetime:
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("aware timestamp required")
    return stamp.astimezone(timezone.utc)


def _safe_pnl(value: object) -> bool:
    return (type(value) is Decimal and value.is_finite() and value.as_tuple().exponent >= -8
            and (value == 0 or value.copy_abs().adjusted() <= 20))


def audit_portfolio_replay_ledger(trades: tuple[ClosedReplay, ...]) -> PortfolioReplayLedgerReceipt:
    """Reject open/duplicate/unordered synthetic trades; deterministic ledger digest."""
    if not isinstance(trades, tuple) or not 1 <= len(trades) <= 5000:
        return PortfolioReplayLedgerReceipt(False, 0, None, '', ('invalid trade batch size',))
    blockers: list[str] = []
    ids: set[str] = set()
    replay_hashes: set[str] = set()
    previous: datetime | None = None
    pnl = Decimal(0)
    canonical: list[dict[str, str]] = []
    for index, trade in enumerate(trades):
        try:
            if not isinstance(trade, ClosedReplay) or not isinstance(trade.trade_id, str) or not _ID.fullmatch(trade.trade_id):
                raise ValueError('invalid trade identity')
            stamp = _as_utc(trade.closed_at)
            evidence = trade.receipt
            if (not isinstance(evidence, E2EPaperReplayReceipt)
                    or evidence.accepted_for_offline_paper_review is not True or evidence.blockers
                    or evidence.live_trading_authorized is not False
                    or evidence.autonomous_execution_authorized is not False
                    or evidence.strategy_promotion_authorized is not False
                    or not isinstance(evidence.replay_sha256, str) or not _HEX.fullmatch(evidence.replay_sha256)
                    or not _safe_pnl(evidence.net_pnl)):
                raise ValueError('unaccepted or malformed Stage 190 receipt')
            if trade.trade_id in ids or evidence.replay_sha256 in replay_hashes:
                raise ValueError('duplicate trade id or replay digest')
            if previous is not None and stamp <= previous:
                raise ValueError('non-increasing close timestamp')
            pnl += evidence.net_pnl
            if not _safe_pnl(pnl):
                raise ValueError('unbounded aggregate pnl')
            ids.add(trade.trade_id)
            replay_hashes.add(evidence.replay_sha256)
            previous = stamp
            canonical.append({'id': trade.trade_id, 'at': stamp.isoformat(timespec='microseconds'),
                              'replay': evidence.replay_sha256, 'net': str(evidence.net_pnl)})
        except (ValueError, TypeError, OverflowError, ArithmeticError) as exc:
            blockers.append(f'trade {index}: {exc}')
            break
    if blockers:
        return PortfolioReplayLedgerReceipt(False, len(canonical), None, '', tuple(blockers))
    raw = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return PortfolioReplayLedgerReceipt(True, len(canonical), pnl,
                                        hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
