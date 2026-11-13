"""Stage 202: point-in-time NSE options/futures contract master consistency.

source_verified on a spec is a caller assertion, not independent exchange proof.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import hashlib
import json

from .instrument_master import PointInTimeContractSpec


@dataclass(frozen=True, slots=True)
class FOContractMasterReceipt:
    accepted_structurally: bool
    contract_master_sha256: str
    underlyings: tuple[str, ...]
    blockers: tuple[str, ...]
    official_exchange_circulars_authenticated: bool = False
    live_trading_authorized: bool = False


def audit_fo_contract_master(specs: tuple[PointInTimeContractSpec, ...], *, asof: date) -> FOContractMasterReceipt:
    errors = []
    records = []
    if type(asof) is not date or not isinstance(specs, tuple) or not 1 <= len(specs) <= 128:
        return FOContractMasterReceipt(False, '', (), ('bounded contracts and date required',))
    seen = set()
    for i, spec in enumerate(specs):
        if type(spec) is not PointInTimeContractSpec:
            errors.append(f'{i}: typed contract required'); continue
        try:
            if spec.exchange != 'NSE' or spec.underlying not in ('NIFTY', 'BANKNIFTY') or spec.segment not in ('OPTIONS', 'FUTURES'):
                raise ValueError('unsupported NSE index F&O instrument')
            if (spec.expiry_date is None or type(spec.expiry_date) is not date or spec.expiry_date < asof
                    or not spec.effective_from <= asof <= spec.effective_to
                    or spec.expiry_date < spec.effective_from):
                raise ValueError('expired or non-point-in-time contract')
            if type(spec.lot_size) is not int or spec.lot_size < 1 or type(spec.freeze_quantity) is not int or spec.freeze_quantity < spec.lot_size:
                raise ValueError('invalid lot or freeze size')
            if not spec.source_reference or spec.source_verified is not True:
                raise ValueError('missing operator-declared metadata reference')
            key = (spec.symbol, spec.expiry_date, spec.segment)
            if key in seen: raise ValueError('duplicate contract identity')
            seen.add(key)
            records.append({'symbol': spec.symbol, 'underlying': spec.underlying, 'segment': spec.segment,
                            'expiry': spec.expiry_date.isoformat(), 'lot': spec.lot_size,
                            'freeze': spec.freeze_quantity, 'tick': str(spec.tick_size),
                            'asof': asof.isoformat(), 'source_ref': spec.source_reference})
        except (TypeError, ValueError, AttributeError) as exc:
            errors.append(f'{i}: {exc}')
    digest = hashlib.sha256(json.dumps(sorted(records, key=lambda x:(x['symbol'],x['expiry'],x['segment'])), sort_keys=True, separators=(',', ':')).encode()).hexdigest() if not errors else ''
    return FOContractMasterReceipt(not errors, digest, tuple(sorted({r['underlying'] for r in records})) if not errors else (), tuple(errors))
