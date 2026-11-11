"""Fail-closed reconciliation for synthetic execution events."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class PaperReconciliation:
    status: str
    total_filled: int
    remaining: int
    weighted_price: float | None
    reasons: tuple[str,...]

def reconcile_paper(*, order_quantity: int, events: tuple[tuple[str,int,float], ...]) -> PaperReconciliation:
    if type(order_quantity) is not int or order_quantity <= 0: raise ValueError('invalid order quantity')
    seen=set(); total=0; value=0.0
    for event in events:
        if not isinstance(event,tuple) or len(event)!=3: raise ValueError('invalid event')
        key,qty,price=event
        if not isinstance(key,str) or not key or key in seen or type(qty) is not int or qty <= 0 or not isinstance(price,(int,float)) or isinstance(price,bool) or not isfinite(price) or price <= 0:
            raise ValueError('duplicate or invalid fill')
        seen.add(key); total+=qty; value+=qty*price
        if total>order_quantity or not isfinite(value): raise ValueError('overfill or overflow')
    status='FILLED' if total==order_quantity else 'PARTIAL' if total else 'UNFILLED'
    return PaperReconciliation(status,total,order_quantity-total,value/total if total else None,('SIMULATED_EVENTS_ONLY',))
