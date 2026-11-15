"""Bounded deterministic fill simulator for research; not a live broker adapter."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ExecutionRequest:
    side: str
    quantity: int
    reference_price: float
    available_quantity: int
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_ms: int = 0
    max_latency_ms: int = 1000
    limit_price: float | None = None

@dataclass(frozen=True)
class ExecutionResult:
    status: str
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float | None
    estimated_cost: float
    reason: str

def simulate_execution(req: ExecutionRequest) -> ExecutionResult:
    if req.side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    ints = (req.quantity, req.available_quantity, req.latency_ms, req.max_latency_ms)
    if any(isinstance(x,bool) or not isinstance(x,int) for x in ints) or req.quantity <= 0 or req.available_quantity < 0 or req.latency_ms < 0 or req.max_latency_ms < 0:
        raise ValueError("Invalid quantity or latency")
    nums = (req.reference_price, req.spread_bps, req.slippage_bps)
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in nums) or req.reference_price <= 0 or req.spread_bps < 0 or req.slippage_bps < 0:
        raise ValueError("Invalid price or execution cost")
    if req.limit_price is not None and (not math.isfinite(req.limit_price) or req.limit_price <= 0):
        raise ValueError("Invalid limit price")
    if req.latency_ms > req.max_latency_ms:
        return ExecutionResult("REJECTED",0,req.quantity,None,0.0,"LATENCY_LIMIT_EXCEEDED")
    fill = min(req.quantity, req.available_quantity)
    if fill == 0:
        return ExecutionResult("REJECTED",0,req.quantity,None,0.0,"NO_AVAILABLE_LIQUIDITY")
    half_spread = req.spread_bps / 20000.0
    slip = req.slippage_bps / 10000.0
    direction = 1 if req.side == "BUY" else -1
    price = req.reference_price * (1 + direction*(half_spread+slip))
    if req.limit_price is not None:
        marketable = price <= req.limit_price if req.side == "BUY" else price >= req.limit_price
        if not marketable:
            return ExecutionResult("UNFILLED",0,req.quantity,None,0.0,"LIMIT_NOT_MARKETABLE")
        price = min(price,req.limit_price) if req.side == "BUY" else max(price,req.limit_price)
    status = "FILLED" if fill == req.quantity else "PARTIAL"
    return ExecutionResult(status,fill,req.quantity-fill,round(price,8),round(abs(price-req.reference_price)*fill,8),"SIMULATED_FILL")
