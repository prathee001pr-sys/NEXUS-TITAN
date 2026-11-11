"""Conservative user-supplied cost/margin estimates; not official NSE/broker margin."""
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation,ROUND_UP

@dataclass(frozen=True)
class CostEstimate:
    notional: Decimal
    estimated_total_cost: Decimal
    margin_required: Decimal
    sufficient_capital: bool
    research_only: bool = True
    live_trading_enabled: bool = False

def _money(x: object) -> Decimal:
    try: d=Decimal(str(x))
    except (InvalidOperation,TypeError,ValueError): raise ValueError('INVALID_AMOUNT') from None
    if not d.is_finite() or d<0: raise ValueError('INVALID_AMOUNT')
    return d

def estimate_cost_margin(*, premium: object, quantity: int, capital: object, brokerage: object, other_fees: object, slippage_per_unit: object, margin_requirement: object) -> CostEstimate:
    if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity<=0: raise ValueError('INVALID_QUANTITY')
    p,c,b,f,s,m=map(_money,(premium,capital,brokerage,other_fees,slippage_per_unit,margin_requirement))
    if p<=0: raise ValueError('INVALID_PREMIUM')
    notional=p*quantity
    costs=(b+f+s*quantity).quantize(Decimal('0.01'),rounding=ROUND_UP)
    required=m+costs
    return CostEstimate(notional,costs,required,c>=required)
