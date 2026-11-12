"""Stage 167: bounded synthetic fill-price sanity checks; not broker execution."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class FillReceipt:
    accepted: bool
    errors: tuple[str, ...]

def audit_fill(*, side: str, reference_price: float, fill_price: float, max_adverse_bps: float) -> FillReceipt:
    values = (reference_price, fill_price, max_adverse_bps)
    if side not in ('BUY', 'SELL') or any(type(x) not in (float, int) or not math.isfinite(x) for x in values):
        return FillReceipt(False, ('invalid inputs',))
    if reference_price <= 0 or fill_price <= 0 or max_adverse_bps < 0:
        return FillReceipt(False, ('invalid price or bound',))
    adverse = ((fill_price - reference_price) if side == 'BUY' else (reference_price - fill_price)) / reference_price * 10000
    return FillReceipt(adverse <= max_adverse_bps, () if adverse <= max_adverse_bps else ('adverse fill exceeds limit',))
