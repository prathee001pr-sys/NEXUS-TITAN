"""Stage 187: signal-to-quote causality. No strategy, broker, or execution access."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from .stage186_quote_tape import TapeQuote, QuoteTapeReceipt, audit_quote_tape
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class SignalIntent:
    signal_id: str
    contract_id: str
    dataset_sha256: str
    tape_sha256: str
    quote_id: str
    decision_at: datetime
    side: str
    quantity: int
    max_slippage_bps: int


@dataclass(frozen=True, slots=True)
class CausalSignalReceipt:
    accepted: bool
    signal_id: str
    contract_id: str
    dataset_sha256: str
    tape_sha256: str
    quote_id: str
    decision_at: datetime | None
    side: str
    quantity: int
    max_slippage_bps: int
    bid: Decimal | None
    ask: Decimal | None
    bid_depth: int
    ask_depth: int
    blockers: tuple[str, ...]


def audit_causal_signal(signal: SignalIntent, *, quotes: tuple[TapeQuote, ...],
                        tape: QuoteTapeReceipt, max_quote_age_ms: int = 1500) -> CausalSignalReceipt:
    failures: list[str] = []
    if not isinstance(signal, SignalIntent) or not isinstance(tape, QuoteTapeReceipt):
        failures.append('invalid signal or quote tape')
    elif (not tape.accepted or tape.blockers or not tape.tape_sha256
          or (signal.contract_id, signal.dataset_sha256, signal.tape_sha256) !=
             (tape.contract_id, tape.dataset_sha256, tape.tape_sha256)):
        failures.append('untrusted or mismatched quote tape')
    if (type(max_quote_age_ms) is not int or not 0 <= max_quote_age_ms <= 86_400_000):
        failures.append('invalid quote age bound')
    if failures:
        return CausalSignalReceipt(False, '', '', '', '', '', None, '', 0, 0, None, None, 0, 0, tuple(failures))
    if not audit_quote_tape(quotes, contract_id=tape.contract_id, dataset_sha256=tape.dataset_sha256) == tape:
        failures.append('quotes do not reproduce tape fingerprint')
    if (not isinstance(signal.signal_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', signal.signal_id)
            or signal.side not in ('BUY', 'SELL') or type(signal.quantity) is not int
            or not 1 <= signal.quantity <= 1_000_000
            or type(signal.max_slippage_bps) is not int or not 0 <= signal.max_slippage_bps <= 1000):
        failures.append('invalid signal identity or limits')
    if not isinstance(signal.decision_at, datetime) or signal.decision_at.tzinfo is None or signal.decision_at.utcoffset() is None:
        failures.append('aware decision timestamp required')
    if failures:
        return CausalSignalReceipt(False, '', '', '', '', '', None, '', 0, 0, None, None, 0, 0, tuple(failures))
    decision = signal.decision_at.astimezone(timezone.utc)
    available = [q for q in quotes if q.available_at.astimezone(timezone.utc) <= decision]
    selected = available[-1] if available else None
    if selected is None or selected.quote_id != signal.quote_id:
        failures.append('signal did not use latest available quote')
    elif type(max_quote_age_ms) is int and decision - selected.available_at.astimezone(timezone.utc) > timedelta(milliseconds=max_quote_age_ms):
        failures.append('quote stale at decision')
    bid = parse_amount(selected.bid) if selected else None
    ask = parse_amount(selected.ask) if selected else None
    return CausalSignalReceipt(not failures, signal.signal_id, signal.contract_id,
                               signal.dataset_sha256, signal.tape_sha256, signal.quote_id,
                               decision, signal.side, signal.quantity, signal.max_slippage_bps,
                               bid, ask, selected.bid_quantity if selected else 0,
                               selected.ask_quantity if selected else 0, tuple(failures))
