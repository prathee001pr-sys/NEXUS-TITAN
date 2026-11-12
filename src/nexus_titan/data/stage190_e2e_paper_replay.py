"""Stage 190: actual read-only module-to-module synthetic E2E replay, fail closed.

No live broker execution, real-fill evidence, strategy promotion, or real-market
backtest certification is created by this function. All receipts are synthetic.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import json
from .stage185_derivatives_review_gate import DerivativesReviewReceipt
from .stage186_quote_tape import TapeQuote, audit_quote_tape
from .stage187_causal_signal import SignalIntent, audit_causal_signal
from .stage188_synthetic_fill import SyntheticFillEvent, audit_synthetic_fills
from .stage189_synthetic_roundtrip import audit_synthetic_roundtrip


@dataclass(frozen=True, slots=True)
class E2EPaperReplayReceipt:
    accepted_for_offline_paper_review: bool
    net_pnl: Decimal | None
    replay_sha256: str
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def replay_synthetic_roundtrip(*, quotes: tuple[TapeQuote, ...], contract_id: str,
                               dataset_sha256: str, entry_signal: SignalIntent,
                               entry_fills: tuple[SyntheticFillEvent, ...],
                               exit_signal: SignalIntent,
                               exit_fills: tuple[SyntheticFillEvent, ...],
                               contract_multiplier: int, entry_fees: str, exit_fees: str,
                               independent_review: DerivativesReviewReceipt | None,
                               source_independently_verified: bool,
                               contract_independently_verified: bool,
                               fee_schedule_independently_verified: bool,
                               risk_veto_independently_verified: bool,
                               live_requested: bool = False,
                               promotion_requested: bool = False,
                               autonomous_requested: bool = False) -> E2EPaperReplayReceipt:
    """Join verified clock/quote/signal/fill/settlement receipts; no side effects."""
    blockers: list[str] = []
    tape = audit_quote_tape(quotes, contract_id=contract_id, dataset_sha256=dataset_sha256)
    if not tape.accepted:
        blockers.append('invalid quote tape')
        return E2EPaperReplayReceipt(False, None, '', tuple(blockers))
    entry = audit_causal_signal(entry_signal, quotes=quotes, tape=tape)
    exit = audit_causal_signal(exit_signal, quotes=quotes, tape=tape)
    if not entry.accepted or not exit.accepted:
        blockers.append('causality or quote provenance failed')
        return E2EPaperReplayReceipt(False, None, '', tuple(blockers))
    # A synthetic fill cannot silently keep using an older quote after a newer
    # quote becomes available. This is a reproducible conservative replay rule.
    for label, intent, fills in (('entry', entry, entry_fills), ('exit', exit, exit_fills)):
        for event in fills:
            if not isinstance(event, SyntheticFillEvent) or not isinstance(event.filled_at, datetime) or event.filled_at.tzinfo is None or event.filled_at.utcoffset() is None:
                blockers.append(f'{label}: invalid fill timestamp or record')
                break
            fresh = [q for q in quotes if q.available_at.astimezone(timezone.utc) <= event.filled_at.astimezone(timezone.utc)]
            if not fresh or fresh[-1].quote_id != intent.quote_id:
                blockers.append(f'{label}: newer quote arrived before synthetic fill')
                break
    if (isinstance(entry_fills, tuple) and isinstance(exit_fills, tuple)
            and all(isinstance(f, SyntheticFillEvent) for f in entry_fills + exit_fills)):
        all_ids = [f.event_id for f in entry_fills + exit_fills]
        if len(set(all_ids)) != len(all_ids):
            blockers.append('duplicate fill event across roundtrip')
    if (entry.decision_at is not None and exit.decision_at is not None
            and entry_fills and isinstance(entry_fills[-1], SyntheticFillEvent)
            and isinstance(entry_fills[-1].filled_at, datetime)
            and entry_fills[-1].filled_at.tzinfo is not None
            and exit.decision_at <= entry_fills[-1].filled_at):
        blockers.append('exit intent predates completed entry fill')
    if blockers:
        return E2EPaperReplayReceipt(False, None, '', tuple(blockers))
    entry_fill = audit_synthetic_fills(entry_fills, signal=entry)
    exit_fill = audit_synthetic_fills(exit_fills, signal=exit)
    roundtrip = audit_synthetic_roundtrip(entry=entry_fill, exit=exit_fill,
                                         multiplier=contract_multiplier,
                                         entry_fees=entry_fees, exit_fees=exit_fees)
    if not roundtrip.accepted or roundtrip.settlement is None:
        blockers.append('fill or closed settlement failed')
    if (not isinstance(independent_review, DerivativesReviewReceipt)
            or independent_review.accepted_for_offline_paper_review is not True
            or independent_review.blockers or independent_review.live_trading_authorized is not False
            or independent_review.autonomous_execution_authorized is not False
            or independent_review.strategy_promotion_authorized is not False):
        blockers.append('Stage 185 review not approved for offline evidence')
    checks = {
        'independent source verification': source_independently_verified is True,
        'independent contract verification': contract_independently_verified is True,
        'independent fee schedule verification': fee_schedule_independently_verified is True,
        'independent risk veto review': risk_veto_independently_verified is True,
        'live order prohibited': live_requested is False,
        'autonomous orders prohibited': autonomous_requested is False,
        'strategy promotion prohibited': promotion_requested is False,
    }
    blockers.extend(label for label, accepted in checks.items() if not accepted)
    if blockers or roundtrip.settlement is None:
        return E2EPaperReplayReceipt(False, None, '', tuple(blockers))
    net = roundtrip.settlement.net_pnl
    raw = json.dumps({'dataset': dataset_sha256, 'tape': tape.tape_sha256,
                      'entry_fill': entry_fill.fills_sha256, 'exit_fill': exit_fill.fills_sha256,
                      'entry_fee': entry_fees, 'exit_fee': exit_fees,
                      'multiplier': contract_multiplier, 'net': str(net)},
                     sort_keys=True, separators=(',', ':'))
    return E2EPaperReplayReceipt(True, net, hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
