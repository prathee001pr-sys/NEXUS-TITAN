"""Deterministic, bounded, research-only limit order fill simulator."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class PaperFill:
    status: str
    filled: int
    remaining: int
    average_price: float | None
    reason: str
    live_enabled: bool = False

def simulate_limit(*, side: str, quantity: int, limit_price: float, bid: float, ask: float, bid_size: int, ask_size: int, slippage: float = 0.0) -> PaperFill:
    if side not in ('BUY','SELL') or type(quantity) is not int or quantity <= 0 or type(bid_size) is not int or type(ask_size) is not int or min(bid_size,ask_size) < 0:
        raise ValueError('invalid order or quote size')
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) for v in (limit_price,bid,ask,slippage)) or min(limit_price,bid,ask) <= 0 or bid > ask or slippage < 0:
        raise ValueError('invalid quote or price')
    price = ask + slippage if side == 'BUY' else bid - slippage
    if price <= 0:
        raise ValueError('invalid adjusted price')
    crosses = price <= limit_price if side == 'BUY' else price >= limit_price
    available = ask_size if side == 'BUY' else bid_size
    filled = min(quantity,available) if crosses else 0
    status = 'FILLED' if filled == quantity else 'PARTIAL' if filled else 'UNFILLED'
    return PaperFill(status,filled,quantity-filled,price if filled else None,'SIMULATED_ONLY')
