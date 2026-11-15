"""Stage 169: deterministic closed-trade accounting sanity (offline only)."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True)
class PerformanceReceipt:
    accepted: bool
    net_pnl: Decimal | None
    errors: tuple[str, ...]

def audit_closed_trades(gross_pnls: tuple[str, ...], costs: tuple[str, ...]) -> PerformanceReceipt:
    if not isinstance(gross_pnls, tuple) or not isinstance(costs, tuple) or not gross_pnls or len(gross_pnls) != len(costs):
        return PerformanceReceipt(False, None, ('missing or mismatched trades',))
    try:
        gross = tuple(Decimal(x) for x in gross_pnls)
        charges = tuple(Decimal(x) for x in costs)
        if any(not x.is_finite() for x in gross + charges) or any(x < 0 for x in charges):
            raise ValueError('invalid amount')
    except (InvalidOperation, ValueError, TypeError):
        return PerformanceReceipt(False, None, ('invalid amounts',))
    return PerformanceReceipt(True, sum((g-c for g,c in zip(gross, charges)), Decimal('0')), ())
