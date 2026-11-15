"""Stage 198: deterministic synthetic closed-ledger replay checks.

This verifies stable in-memory normalization, not crash durability or broker
reconciliation. Stronger durability requires external persisted replay evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import hashlib
import json

from .stage191_portfolio_replay_ledger import (
    ClosedReplay, PortfolioReplayLedgerReceipt, audit_portfolio_replay_ledger,
)


@dataclass(frozen=True, slots=True)
class ReplayStabilityReceipt:
    accepted: bool
    ledger_sha256: str
    replay_stability_sha256: str
    blockers: tuple[str, ...]


def audit_replay_stability(trades: tuple[ClosedReplay, ...], *,
                           ledger: PortfolioReplayLedgerReceipt) -> ReplayStabilityReceipt:
    if type(ledger) is not PortfolioReplayLedgerReceipt:
        return ReplayStabilityReceipt(False, '', '', ('missing Stage 191 receipt',))
    verified = audit_portfolio_replay_ledger(trades)
    if not verified.accepted or verified != ledger:
        return ReplayStabilityReceipt(False, '', '', ('Stage 191 receipt mismatch',))
    # Normalizing offset-aware timestamps must not change the ledger digest.
    normalized = tuple(ClosedReplay(t.trade_id, t.closed_at.astimezone(timezone.utc), t.receipt)
                       for t in trades)
    replayed = audit_portfolio_replay_ledger(normalized)
    if not replayed.accepted or replayed != ledger or audit_portfolio_replay_ledger(trades) != ledger:
        return ReplayStabilityReceipt(False, '', '', ('non-deterministic normalized replay',))
    raw = json.dumps({'ledger': ledger.ledger_sha256, 'trade_count': ledger.trade_count,
                      'net_pnl': str(ledger.net_pnl), 'normalization': 'utc'},
                     sort_keys=True, separators=(',', ':'))
    return ReplayStabilityReceipt(True, ledger.ledger_sha256,
                                  hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
