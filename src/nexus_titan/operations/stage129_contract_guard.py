"""Research-only option contract validation; no order routing."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True)
class ContractReview:
    underlying: str
    expiry: str
    strike: str
    side: str
    valid: bool
    reasons: tuple[str, ...]
    trading_approved: bool = False

def review_contract(underlying: str, expiry: str, strike: object, side: str, *, as_of: str) -> ContractReview:
    reasons=[]
    if underlying not in ('NIFTY','BANKNIFTY'): reasons.append('UNSUPPORTED_UNDERLYING')
    if side not in ('CE','PE'): reasons.append('INVALID_OPTION_SIDE')
    try:
        d=date.fromisoformat(expiry); today=date.fromisoformat(as_of)
        if d<today: reasons.append('EXPIRED_CONTRACT')
    except (ValueError,TypeError): reasons.append('INVALID_DATE')
    try:
        k=Decimal(str(strike))
        if not k.is_finite() or k<=0: reasons.append('INVALID_STRIKE')
    except (InvalidOperation,ValueError,TypeError): reasons.append('INVALID_STRIKE')
    return ContractReview(underlying,expiry,str(strike),side,not reasons,tuple(reasons))
