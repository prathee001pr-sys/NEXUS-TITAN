"""Stage 157: strict metadata checks for Indian F&O contracts, without trading."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import math

@dataclass(frozen=True)
class ContractReceipt:
    accepted: bool
    errors: tuple[str, ...]

def validate_fo_contract(*, symbol: str, instrument: str, expiry: date,
                         asof: date, strike: float | None = None,
                         option_type: str | None = None, lot_size: int = 1) -> ContractReceipt:
    errors = []
    if symbol not in ('NIFTY', 'BANKNIFTY'): errors.append('unsupported symbol')
    if instrument not in ('FUT', 'OPT'): errors.append('unsupported instrument')
    if type(asof) is not date or type(expiry) is not date or (type(asof) is date and type(expiry) is date and expiry < asof):
        errors.append('invalid expiry or asof')
    if type(lot_size) is not int or lot_size <= 0: errors.append('invalid lot size')
    if instrument == 'OPT':
        if option_type not in ('CE', 'PE'): errors.append('invalid option type')
        if type(strike) not in (int, float) or not math.isfinite(strike) or strike <= 0: errors.append('invalid strike')
    elif instrument == 'FUT' and (strike is not None or option_type is not None):
        errors.append('future must not contain option fields')
    return ContractReceipt(not errors, tuple(errors))
