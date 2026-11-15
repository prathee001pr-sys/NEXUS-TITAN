"""Stage 186: deterministic read-only quote tape integrity (synthetic/offline only).

An internally consistent tape is NOT proof of genuine exchange data or contract eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from .stage176_quote_sanity import parse_amount

_CONTRACT = re.compile(r'[A-Z0-9:_-]{3,100}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class TapeQuote:
    quote_id: str
    observed_at: datetime
    available_at: datetime
    bid: str
    ask: str
    bid_quantity: int
    ask_quantity: int


@dataclass(frozen=True, slots=True)
class QuoteTapeReceipt:
    accepted: bool
    contract_id: str
    dataset_sha256: str
    tape_sha256: str
    quote_count: int
    blockers: tuple[str, ...]


def _utc_stamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware clock required')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def audit_quote_tape(quotes: tuple[TapeQuote, ...], *, contract_id: str,
                     dataset_sha256: str) -> QuoteTapeReceipt:
    """Validate a bounded, immutable event sequence and hash canonical fields."""
    blockers: list[str] = []
    if not isinstance(contract_id, str) or not _CONTRACT.fullmatch(contract_id):
        blockers.append('invalid contract identity')
    if not isinstance(dataset_sha256, str) or not _SHA256.fullmatch(dataset_sha256):
        blockers.append('invalid dataset fingerprint')
    if not isinstance(quotes, tuple) or not 2 <= len(quotes) <= 10000:
        return QuoteTapeReceipt(False, '', '', '', 0, tuple(blockers + ['invalid quote count']))
    previous_observed: datetime | None = None
    previous_available: datetime | None = None
    identities: set[str] = set()
    canonical: list[dict[str, object]] = []
    for i, q in enumerate(quotes):
        if not isinstance(q, TapeQuote):
            blockers.append(f'quote {i}: invalid type')
            break
        try:
            if (not isinstance(q.quote_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', q.quote_id)
                    or q.quote_id in identities or type(q.bid_quantity) is not int
                    or type(q.ask_quantity) is not int
                    or not 1 <= q.bid_quantity <= 1_000_000
                    or not 1 <= q.ask_quantity <= 1_000_000):
                raise ValueError('invalid quote identifier or depth')
            bid, ask = parse_amount(q.bid), parse_amount(q.ask)
            if bid <= 0 or ask < bid:
                raise ValueError('invalid bid/ask')
            observed_text, available_text = _utc_stamp(q.observed_at), _utc_stamp(q.available_at)
            observed = q.observed_at.astimezone(timezone.utc)
            available = q.available_at.astimezone(timezone.utc)
            if available < observed:
                raise ValueError('quote available before observed')
            if (previous_observed is not None and observed <= previous_observed) or (previous_available is not None and available <= previous_available):
                raise ValueError('non-increasing tape clocks')
            identities.add(q.quote_id)
            previous_observed, previous_available = observed, available
            canonical.append({'id': q.quote_id, 'observed': observed_text,
                              'available': available_text, 'bid': str(bid.normalize()),
                              'ask': str(ask.normalize()), 'bid_qty': q.bid_quantity,
                              'ask_qty': q.ask_quantity})
        except (ValueError, TypeError, OverflowError):
            blockers.append(f'quote {i}: malformed or inconsistent')
            break
    digest = ''
    if not blockers:
        raw = json.dumps({'contract': contract_id, 'dataset': dataset_sha256, 'quotes': canonical},
                         sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        digest = hashlib.sha256(raw.encode('ascii')).hexdigest()
    return QuoteTapeReceipt(not blockers, contract_id if not blockers else '',
                            dataset_sha256 if not blockers else '', digest,
                            len(canonical), tuple(blockers))
