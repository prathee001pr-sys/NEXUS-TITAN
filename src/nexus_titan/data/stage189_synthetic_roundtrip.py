"""Stage 189: join two synthetic fills to the existing Stage 173 net settlement ledger."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .stage173_settlement_ledger import SettlementReceipt, audit_roundtrip_settlement
from .stage188_synthetic_fill import SyntheticFillReceipt


@dataclass(frozen=True, slots=True)
class RoundTripReplayReceipt:
    accepted: bool
    contract_id: str
    dataset_sha256: str
    tape_sha256: str
    quantity: int
    settlement: SettlementReceipt | None
    blockers: tuple[str, ...]


def audit_synthetic_roundtrip(*, entry: SyntheticFillReceipt, exit: SyntheticFillReceipt,
                              multiplier: int, entry_fees: str, exit_fees: str) -> RoundTripReplayReceipt:
    failures: list[str] = []
    for label, receipt in (('entry', entry), ('exit', exit)):
        if not isinstance(receipt, SyntheticFillReceipt) or not receipt.accepted or not receipt.fully_filled or receipt.blockers:
            failures.append(f'{label} synthetic fill incomplete or invalid')
    if failures:
        return RoundTripReplayReceipt(False, '', '', '', 0, None, tuple(failures))
    if (entry.contract_id != exit.contract_id or entry.dataset_sha256 != exit.dataset_sha256
            or entry.tape_sha256 != exit.tape_sha256 or not entry.tape_sha256
            or entry.signal_id == exit.signal_id or not entry.fills_sha256 or not exit.fills_sha256):
        failures.append('roundtrip identity or provenance mismatch')
    if entry.side == exit.side or entry.side not in ('BUY', 'SELL') or exit.side not in ('BUY', 'SELL'):
        failures.append('roundtrip not closed with opposite side')
    if entry.quantity <= 0 or entry.quantity != exit.quantity:
        failures.append('open exposure or mismatched exit quantity')
    if (not isinstance(entry.last_fill_at, datetime) or not isinstance(exit.last_fill_at, datetime)
            or entry.last_fill_at >= exit.last_fill_at):
        failures.append('exit not after entry')
    if entry.average_price is None or exit.average_price is None:
        failures.append('missing synthetic prices')
    if failures:
        return RoundTripReplayReceipt(False, '', '', '', 0, None, tuple(failures))
    settlement = audit_roundtrip_settlement(
        entry_side=entry.side, entry_price=str(entry.average_price),
        exit_price=str(exit.average_price), quantity=str(entry.quantity),
        contract_multiplier=multiplier, entry_fees=entry_fees, exit_fees=exit_fees)
    if not settlement.accepted or settlement.blockers:
        failures.append('Stage 173 settlement rejected fees or quantities')
    return RoundTripReplayReceipt(not failures, entry.contract_id, entry.dataset_sha256,
                                  entry.tape_sha256, entry.quantity,
                                  settlement if not failures else None, tuple(failures))
