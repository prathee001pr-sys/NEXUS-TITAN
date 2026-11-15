"""Stage 209: deterministic bounded order-size/latency/fee stress grid.

Scenario inputs are hypothetical, NOT observed queue position, market impact,
exchange latency, exchange liquidity, real fills or execution assurances.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

from .stage206_depth_snapshot import DepthSnapshot, DepthSnapshotReceipt
from .stage207_liquidity_fill import audit_liquidity_fill
from .stage208_fee_sensitivity import FeeScenario, audit_fee_sensitivity

_NAME = re.compile(r'[a-z][a-z0-9_-]{0,39}\Z')


@dataclass(frozen=True, slots=True)
class CapacityCase:
    name: str
    order_quantity: int
    participation_bps: int
    simulated_latency_ms: int
    max_slippage_bps: int
    max_fee_cost_bps: int


@dataclass(frozen=True, slots=True)
class CapacityStressReceipt:
    accepted: bool
    snapshot_sha256: str
    capacity_sha256: str
    scenario_count: int
    passed_count: int
    failed_scenarios: tuple[str, ...]
    blockers: tuple[str, ...]
    real_market_capacity_verified: bool = False
    live_trading_authorized: bool = False


def audit_capacity_stress(snapshot: DepthSnapshot, *, depth: DepthSnapshotReceipt,
                          side: str, cases: tuple[CapacityCase, ...],
                          fees: FeeScenario, contract_multiplier: int = 1,
                          tick_size: str = '0.05', max_age_ms: int = 1500,
                          max_spread_bps: int = 1000) -> CapacityStressReceipt:
    errors: list[str] = []
    if type(depth) is not DepthSnapshotReceipt or not depth.accepted or depth.blockers:
        errors.append('invalid linked depth receipt')
    if not isinstance(cases, tuple) or not 1 <= len(cases) <= 12:
        errors.append('bounded scenario list required')
    if type(fees) is not FeeScenario:
        errors.append('invalid fee assumptions')
    if side not in ('BUY', 'SELL'):
        errors.append('invalid scenario side')
    if errors:
        return CapacityStressReceipt(False, '', '', 0, 0, (), tuple(errors))
    seen: set[str] = set()
    failed: list[str] = []
    canonical: list[dict[str, object]] = []
    for case in cases:
        if (type(case) is not CapacityCase or not isinstance(case.name, str)
                or not _NAME.fullmatch(case.name) or case.name in seen
                or type(case.order_quantity) is not int or not 1 <= case.order_quantity <= 1_000_000
                or type(case.participation_bps) is not int or not 1 <= case.participation_bps <= 10000
                or type(case.simulated_latency_ms) is not int or not 0 <= case.simulated_latency_ms <= 86_400_000
                or type(case.max_slippage_bps) is not int or not 0 <= case.max_slippage_bps <= 10000
                or type(case.max_fee_cost_bps) is not int or not 0 <= case.max_fee_cost_bps <= 10000):
            errors.append('invalid or duplicate bounded capacity scenario')
            break
        seen.add(case.name)
        execution = audit_liquidity_fill(
            snapshot, depth=depth, side=side, quantity=case.order_quantity,
            participation_bps=case.participation_bps,
            max_adverse_slippage_bps=case.max_slippage_bps,
            latency_ms=case.simulated_latency_ms,
            tick_size=tick_size, max_age_ms=max_age_ms, max_spread_bps=max_spread_bps)
        fee = audit_fee_sensitivity(execution, scenario=fees, contract_multiplier=contract_multiplier)
        fee_bps = (fee.total_assumed_cost * 10000 / fee.monetary_notional
                   if fee.accepted and fee.total_assumed_cost is not None and fee.monetary_notional
                   else None)
        passed = bool(execution.accepted and execution.fully_filled and fee.accepted
                      and fee_bps is not None and fee_bps <= case.max_fee_cost_bps)
        if not passed:
            failed.append(case.name)
        canonical.append({'name': case.name, 'quantity': case.order_quantity,
                          'participation': case.participation_bps,
                          'latency': case.simulated_latency_ms,
                          'slippage_cap': case.max_slippage_bps,
                          'fee_cap': case.max_fee_cost_bps,
                          'fill': execution.fill_sha256, 'fee': fee.fee_sha256,
                          'fee_bps': str(fee_bps) if fee_bps is not None else None,
                          'passed': passed})
    if errors:
        return CapacityStressReceipt(False, '', '', len(canonical),
                                     len(canonical)-len(failed), tuple(failed), tuple(errors))
    if failed:
        errors.append('one or more synthetic capacity scenarios failed')
    raw = json.dumps({'depth':depth.snapshot_sha256, 'side':side,'cases':canonical},
                     sort_keys=True,separators=(',',':'))
    return CapacityStressReceipt(not errors, depth.snapshot_sha256,
                                 hashlib.sha256(raw.encode()).hexdigest() if not errors else '',
                                 len(canonical), len(canonical)-len(failed), tuple(failed), tuple(errors))
