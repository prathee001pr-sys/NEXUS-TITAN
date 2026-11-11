"""Explicit user-supplied cost rates, no exchange fee assumptions."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class PaperCosts:
    gross_notional: float
    brokerage: float
    statutory_and_exchange: float
    total_cost: float
    assumptions_verified: bool = False

def estimate_paper_costs(*, quantity: int, price: float, brokerage_flat: float, fee_rate: float) -> PaperCosts:
    if type(quantity) is not int or quantity <= 0:
        raise ValueError('invalid quantity')
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) or v < 0 for v in (price,brokerage_flat,fee_rate)) or price == 0 or fee_rate > 1:
        raise ValueError('invalid cost inputs')
    notional=quantity*price
    if not isfinite(notional): raise ValueError('notional overflow')
    fees=notional*fee_rate
    return PaperCosts(notional,brokerage_flat,fees,brokerage_flat+fees)
