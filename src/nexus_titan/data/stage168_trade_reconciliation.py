"""Stage 168: synthetic order/fill quantity reconciliation; no broker calls."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True)
class ReconciliationReceipt:
    accepted: bool
    filled: Decimal | None
    errors: tuple[str, ...]

def reconcile_quantities(requested: str, fills: tuple[str, ...]) -> ReconciliationReceipt:
    try:
        q = Decimal(requested)
        amounts = tuple(Decimal(v) for v in fills)
        if not q.is_finite() or q <= 0 or any(not x.is_finite() or x <= 0 for x in amounts):
            raise ValueError('nonpositive or nonfinite quantity')
        if not isinstance(fills, tuple) or not fills:
            raise ValueError('missing fills')
    except (InvalidOperation, ValueError, TypeError):
        return ReconciliationReceipt(False, None, ('invalid quantities',))
    total = sum(amounts, Decimal('0'))
    if total > q:
        return ReconciliationReceipt(False, total, ('overfill',))
    if total < q:
        return ReconciliationReceipt(False, total, ('partial fill',))
    return ReconciliationReceipt(True, total, ())
