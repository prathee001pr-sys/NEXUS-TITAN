"""Stage 193: extra fixed per-roundtrip cost scenario, offline synthetic sensitivity only.

Not an exchange fee engine. No assumptions about order fills or liquidity beyond
prior receipts; these are additional assumed costs, never rebates.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from .stage176_quote_sanity import parse_amount
from .stage191_portfolio_replay_ledger import (
    ClosedReplay, PortfolioReplayLedgerReceipt, audit_portfolio_replay_ledger,
)


@dataclass(frozen=True, slots=True)
class ExtraCostStressReceipt:
    accepted: bool
    ledger_sha256: str
    stressed_net_pnl: Decimal | None
    cost_sha256: str
    blockers: tuple[str, ...]


def audit_extra_cost_stress(trades: tuple[ClosedReplay, ...], *, ledger: PortfolioReplayLedgerReceipt,
                            extra_cost_per_roundtrip: str,
                            max_acceptable_loss: str) -> ExtraCostStressReceipt:
    errors: list[str] = []
    checked = audit_portfolio_replay_ledger(trades)
    if not isinstance(ledger, PortfolioReplayLedgerReceipt) or not checked.accepted or ledger != checked:
        errors.append('unlinked replay ledger')
    try:
        cost = parse_amount(extra_cost_per_roundtrip)
        loss_cap = parse_amount(max_acceptable_loss)
        if any(x < 0 or x.adjusted() > 20 or x.as_tuple().exponent < -8 for x in (cost, loss_cap)):
            raise ValueError('negative, excessive or overprecise scenario cost')
    except (ValueError, TypeError, InvalidOperation):
        errors.append('invalid cost stress inputs')
        cost = loss_cap = Decimal(0)
    if errors:
        return ExtraCostStressReceipt(False, '', None, '', tuple(errors))
    stressed = ledger.net_pnl - cost * ledger.trade_count
    if stressed < -loss_cap:
        errors.append('additional assumed costs exceed loss tolerance')
    if errors:
        return ExtraCostStressReceipt(False, ledger.ledger_sha256, stressed, '', tuple(errors))
    encoded = json.dumps({'ledger': ledger.ledger_sha256, 'count': ledger.trade_count,
                          'extra_cost': str(cost), 'loss_cap': str(loss_cap),
                          'stressed_net': str(stressed)}, sort_keys=True, separators=(',', ':'))
    return ExtraCostStressReceipt(True, ledger.ledger_sha256, stressed,
                                  hashlib.sha256(encoded.encode('ascii')).hexdigest(), ())
