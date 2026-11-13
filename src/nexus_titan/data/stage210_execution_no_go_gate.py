"""Stage 210: replay and cross-check synthetic execution evidence; always NO-GO live.

This gate can admit only *internal synthetic/manual research review*. Neither
Stage205 nor an accepted receipt verifies exchange data, fee rules, broker
execution, liquidity, safety for production, or live-trading authorization.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re

from .stage205_fo_data_readiness_gate import FODataReadinessReceipt
from .stage206_depth_snapshot import DepthSnapshot, DepthSnapshotReceipt, audit_depth_snapshot
from .stage207_liquidity_fill import LiquidityFillReceipt, audit_liquidity_fill
from .stage208_fee_sensitivity import FeeScenario, FeeSensitivityReceipt, audit_fee_sensitivity
from .stage209_capacity_stress import CapacityCase, CapacityStressReceipt, audit_capacity_stress

_SHA = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class SyntheticExecutionNoGoReceipt:
    eligible_for_internal_synthetic_execution_review: bool
    evidence_sha256: str
    blockers: tuple[str, ...]
    real_market_liquidity_verified: bool = False
    exchange_fee_schedule_verified: bool = False
    historical_execution_verified: bool = False
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_execution_no_go_gate(*, snapshot: DepthSnapshot, depth: DepthSnapshotReceipt,
                                  fill: LiquidityFillReceipt, fees: FeeSensitivityReceipt,
                                  capacity: CapacityStressReceipt,
                                  data_readiness: FODataReadinessReceipt,
                                  side: str, quantity: int, participation_bps: int,
                                  max_adverse_slippage_bps: int, latency_ms: int,
                                  fee_scenario: FeeScenario, cases: tuple[CapacityCase, ...],
                                  contract_multiplier: int = 1, tick_size: str = '0.05',
                                  max_age_ms: int = 1500, max_spread_bps: int = 1000,
                                  live_requested: bool = False,
                                  autonomous_requested: bool = False,
                                  promotion_requested: bool = False) -> SyntheticExecutionNoGoReceipt:
    checks: dict[str, bool] = {}
    checks['Stage205 internal-only data readiness'] = (
        type(data_readiness) is FODataReadinessReceipt
        and data_readiness.eligible_for_internal_manual_dataset_review is True
        and not data_readiness.blockers
        and isinstance(data_readiness.linked_evidence_sha256, str)
        and bool(_SHA.fullmatch(data_readiness.linked_evidence_sha256))
        and data_readiness.independent_vendor_authenticated is False
        and data_readiness.source_licence_authenticated is False
        and data_readiness.exchange_metadata_authenticated is False
        and data_readiness.real_historical_data_verified is False
        and data_readiness.real_market_backtest_verified is False
        and data_readiness.live_trading_authorized is False
        and data_readiness.autonomous_execution_authorized is False
        and data_readiness.strategy_promotion_authorized is False)
    checks['Stage206 linked depth'] = (type(depth) is DepthSnapshotReceipt
                                       and depth.accepted is True and not depth.blockers
                                       and depth.live_trading_authorized is False)
    if checks['Stage206 linked depth']:
        recalculated_depth = audit_depth_snapshot(snapshot, decision_at=depth.decision_at,
                                                  tick_size=tick_size, max_age_ms=max_age_ms,
                                                  max_spread_bps=max_spread_bps)
        checks['Stage206 reproduces from input levels'] = depth == recalculated_depth
    else:
        checks['Stage206 reproduces from input levels'] = False
    if checks['Stage206 reproduces from input levels']:
        recalculated_fill = audit_liquidity_fill(snapshot, depth=depth, side=side,
                                                quantity=quantity, participation_bps=participation_bps,
                                                max_adverse_slippage_bps=max_adverse_slippage_bps,
                                                latency_ms=latency_ms, tick_size=tick_size,
                                                max_age_ms=max_age_ms, max_spread_bps=max_spread_bps)
        checks['Stage207 fully filled causal simulation'] = (
            type(fill) is LiquidityFillReceipt and fill == recalculated_fill
            and fill.accepted is True and fill.fully_filled is True and not fill.blockers
            and fill.live_trading_authorized is False)
    else:
        checks['Stage207 fully filled causal simulation'] = False
    if checks['Stage207 fully filled causal simulation']:
        recalculated_fees = audit_fee_sensitivity(fill, scenario=fee_scenario,
                                                  contract_multiplier=contract_multiplier)
        checks['Stage208 explicit assumed fee schedule'] = (
            type(fees) is FeeSensitivityReceipt and fees == recalculated_fees
            and fees.accepted is True and not fees.blockers
            and fees.schedule_independently_verified is False
            and fees.live_trading_authorized is False)
    else:
        checks['Stage208 explicit assumed fee schedule'] = False
    if checks['Stage208 explicit assumed fee schedule']:
        recalculated_capacity = audit_capacity_stress(snapshot, depth=depth, side=side,
                                                       cases=cases, fees=fee_scenario,
                                                       contract_multiplier=contract_multiplier,
                                                       tick_size=tick_size, max_age_ms=max_age_ms,
                                                       max_spread_bps=max_spread_bps)
        checks['Stage209 includes baseline scenario'] = (
            isinstance(cases, tuple) and any(
                type(c) is CapacityCase and c.order_quantity == quantity
                and c.participation_bps == participation_bps
                and c.simulated_latency_ms == latency_ms
                and c.max_slippage_bps == max_adverse_slippage_bps
                for c in cases))
        checks['Stage209 all scenarios pass'] = (
            type(capacity) is CapacityStressReceipt and capacity == recalculated_capacity
            and capacity.accepted is True and not capacity.blockers
            and capacity.scenario_count >= 1 and capacity.scenario_count == capacity.passed_count
            and capacity.real_market_capacity_verified is False
            and capacity.live_trading_authorized is False)
    else:
        checks['Stage209 all scenarios pass'] = False
        checks['Stage209 includes baseline scenario'] = False
    checks['live orders prohibited'] = live_requested is False
    checks['autonomous orders prohibited'] = autonomous_requested is False
    checks['strategy promotion prohibited'] = promotion_requested is False
    blockers = tuple(key for key, ok in checks.items() if not ok)
    digest = ''
    if not blockers:
        body = {'stage205': data_readiness.linked_evidence_sha256,
                'depth': depth.snapshot_sha256, 'fill': fill.fill_sha256,
                'fees': fees.fee_sha256, 'capacity': capacity.capacity_sha256,
                'scope': 'internal_synthetic_execution_review_NO_GO'}
        digest = hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return SyntheticExecutionNoGoReceipt(not blockers, digest, blockers)
