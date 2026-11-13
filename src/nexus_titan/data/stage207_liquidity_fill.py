"""Stage 207: deterministic *hypothetical* depth walk with explicit partial fills.

Quantity at displayed levels is NOT real fill probability or guaranteed capacity.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
import hashlib
import json

from .stage206_depth_snapshot import DepthSnapshot, DepthSnapshotReceipt, audit_depth_snapshot
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class LiquidityFillReceipt:
    accepted: bool
    fully_filled: bool
    snapshot_sha256: str
    fill_sha256: str
    side: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    average_price: Decimal | None
    execution_notional: Decimal | None
    adverse_slippage_bps: Decimal | None
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False


def audit_liquidity_fill(snapshot: DepthSnapshot, *, depth: DepthSnapshotReceipt,
                         side: str, quantity: int, participation_bps: int = 10000,
                         max_adverse_slippage_bps: int = 250,
                         latency_ms: int = 0,
                         tick_size: str = '0.05', max_age_ms: int = 1500,
                         max_spread_bps: int = 1000) -> LiquidityFillReceipt:
    errors: list[str] = []
    def failed() -> LiquidityFillReceipt:
        return LiquidityFillReceipt(False, False, '', '', '', 0, 0, 0, None, None, None, tuple(errors))
    if (type(snapshot) is not DepthSnapshot or type(depth) is not DepthSnapshotReceipt
            or not depth.accepted or depth.blockers or not depth.snapshot_sha256 or depth.decision_at is None):
        errors.append('invalid depth evidence')
        return failed()
    reproduced = audit_depth_snapshot(snapshot, decision_at=depth.decision_at,
                                      tick_size=tick_size, max_age_ms=max_age_ms,
                                      max_spread_bps=max_spread_bps)
    if depth != reproduced:
        errors.append('depth fingerprint does not reproduce')
    if side not in ('BUY', 'SELL') or type(quantity) is not int or not 1 <= quantity <= 1_000_000:
        errors.append('invalid side or requested quantity')
    if type(participation_bps) is not int or not 1 <= participation_bps <= 10000:
        errors.append('invalid participation bound')
    if type(max_adverse_slippage_bps) is not int or not 0 <= max_adverse_slippage_bps <= 10000:
        errors.append('invalid slippage bound')
    if type(latency_ms) is not int or not 0 <= latency_ms <= 86400000:
        errors.append('invalid latency assumption')
    if errors:
        return failed()
    if depth.available_at is None or depth.decision_at - depth.available_at > timedelta(milliseconds=max_age_ms - latency_ms):
        errors.append('stale after assumed latency')
        return failed()
    levels = snapshot.asks if side == 'BUY' else snapshot.bids
    best = depth.best_ask if side == 'BUY' else depth.best_bid
    if best is None:
        errors.append('missing quote reference')
        return failed()
    filled = 0
    notional = Decimal(0)
    walked: list[tuple[str, int]] = []
    for level in levels:
        available = int((Decimal(level.quantity) * Decimal(participation_bps) / 10000).to_integral_value(rounding=ROUND_DOWN))
        take = min(quantity - filled, available)
        if take > 0:
            price = parse_amount(level.price)
            notional += price * take
            filled += take
            walked.append((str(price.normalize()), take))
        if filled == quantity:
            break
    if filled == 0:
        errors.append('no executable synthetic depth')
        return failed()
    average = notional / filled
    slip = ((average - best) if side == 'BUY' else (best - average)) * 10000 / best
    if slip < 0:
        errors.append('impossible improving depth walk')
    if slip > max_adverse_slippage_bps:
        errors.append('depth-walk slippage exceeds policy')
    if errors:
        return LiquidityFillReceipt(False, False, depth.snapshot_sha256, '', side, quantity,
                                    filled, quantity-filled, average, notional, slip, tuple(errors))
    canonical = {'book': depth.snapshot_sha256, 'side': side, 'requested': quantity,
                 'participation_bps': participation_bps, 'slippage_cap': max_adverse_slippage_bps,
                 'latency_ms': latency_ms, 'walked': walked}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return LiquidityFillReceipt(True, filled == quantity, depth.snapshot_sha256, digest,
                                side, quantity, filled, quantity-filled, average, notional, slip, ())
