"""Stage 162: fail-closed F&O chain metadata consistency, no market prices."""
from dataclasses import dataclass
from datetime import date
from .stage157_fo_contract_quality import validate_fo_contract

@dataclass(frozen=True)
class ChainAudit:
    accepted: bool
    errors: tuple[str, ...]

def audit_contract_chain(contracts: tuple[dict, ...], *, asof: date) -> ChainAudit:
    if type(asof) is not date or not isinstance(contracts, tuple) or not contracts:
        return ChainAudit(False, ('invalid asof or empty chain',))
    errors=[]; seen=set()
    for idx, c in enumerate(contracts):
        if not isinstance(c, dict):
            errors.append(f'{idx}: invalid contract'); continue
        try:
            receipt=validate_fo_contract(asof=asof, **c)
            if not receipt.accepted: errors.append(f'{idx}: invalid contract metadata')
            key=(c['symbol'], c['instrument'], c['expiry'], c.get('strike'), c.get('option_type'))
            if key in seen: errors.append(f'{idx}: duplicate contract')
            seen.add(key)
        except (KeyError, TypeError, ValueError):
            errors.append(f'{idx}: malformed contract')
    return ChainAudit(not errors, tuple(errors))
