"""Stage 163: explicit finite nonnegative execution cost assumptions."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class CostAudit:
    accepted: bool
    total_bps: float | None
    errors: tuple[str, ...]

def audit_costs(*, brokerage_bps: float, taxes_bps: float, spread_bps: float, slippage_bps: float) -> CostAudit:
    fields={'brokerage':brokerage_bps,'taxes':taxes_bps,'spread':spread_bps,'slippage':slippage_bps}
    errors=tuple(k for k,v in fields.items() if type(v) not in (float,int) or not math.isfinite(v) or v < 0)
    return CostAudit(not errors, sum(fields.values()) if not errors else None, errors)
