"""Stage 208: bounded *assumed* Indian F&O fee/tax and price-friction scenarios.

No exchange, statutory rate, broker tariff or contract multiplier is authenticated.
Do not use for tax filing or real order placement.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json

from .stage176_quote_sanity import parse_amount
from .stage207_liquidity_fill import LiquidityFillReceipt


@dataclass(frozen=True, slots=True)
class FeeScenario:
    brokerage_fixed: str
    stt_sell_bps: int
    exchange_bps: int
    sebi_bps: int
    gst_bps: int
    stamp_buy_bps: int
    extra_price_friction_bps: int
    other_fixed: str = '0'


@dataclass(frozen=True, slots=True)
class FeeSensitivityReceipt:
    accepted: bool
    fill_sha256: str
    fee_sha256: str
    monetary_notional: Decimal | None
    brokerage: Decimal | None
    stt: Decimal | None
    exchange: Decimal | None
    sebi: Decimal | None
    gst: Decimal | None
    stamp: Decimal | None
    additional_price_friction: Decimal | None
    total_assumed_cost: Decimal | None
    blockers: tuple[str, ...]
    schedule_independently_verified: bool = False
    live_trading_authorized: bool = False


def audit_fee_sensitivity(fill: LiquidityFillReceipt, *, scenario: FeeScenario,
                          contract_multiplier: int = 1) -> FeeSensitivityReceipt:
    errors: list[str] = []
    def rejected():
        return FeeSensitivityReceipt(False, '', '', None, None, None, None, None,
                                     None, None, None, None, tuple(errors))
    if (type(fill) is not LiquidityFillReceipt or not fill.accepted or fill.blockers
            or not fill.fill_sha256 or fill.filled_quantity <= 0
            or fill.execution_notional is None or not fill.execution_notional.is_finite()
            or fill.execution_notional <= 0 or fill.side not in ('BUY', 'SELL')):
        errors.append('missing accepted synthetic fill')
    if type(scenario) is not FeeScenario:
        errors.append('missing scenario')
    if type(contract_multiplier) is not int or not 1 <= contract_multiplier <= 1_000_000:
        errors.append('invalid contract multiplier')
    if errors:
        return rejected()
    try:
        rates = [scenario.stt_sell_bps, scenario.exchange_bps, scenario.sebi_bps,
                 scenario.gst_bps, scenario.stamp_buy_bps, scenario.extra_price_friction_bps]
        if any(type(v) is not int or not 0 <= v <= 10000 for v in rates):
            raise ValueError('invalid fee-rate scenarios')
        fixed, other = parse_amount(scenario.brokerage_fixed), parse_amount(scenario.other_fixed)
        if fixed > 1_000_000 or other > 1_000_000:
            raise ValueError('unbounded fixed fee')
    except (ValueError, TypeError):
        errors.append('invalid fee assumptions')
        return rejected()
    notional = fill.execution_notional * contract_multiplier
    bps = lambda value: notional * Decimal(value) / Decimal(10000)
    brokerage = fixed
    exchange = bps(scenario.exchange_bps)
    sebi = bps(scenario.sebi_bps)
    stt = bps(scenario.stt_sell_bps) if fill.side == 'SELL' else Decimal(0)
    stamp = bps(scenario.stamp_buy_bps) if fill.side == 'BUY' else Decimal(0)
    gst = (brokerage + exchange + sebi) * Decimal(scenario.gst_bps) / Decimal(10000)
    extra = bps(scenario.extra_price_friction_bps)
    total = brokerage + stt + exchange + sebi + gst + stamp + extra + other
    inputs = {'fill': fill.fill_sha256, 'multiplier': contract_multiplier,
              'scenario': [str(fixed.normalize()), *rates, str(other.normalize())],
              'notional': str(notional.normalize()), 'cost': str(total.normalize())}
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return FeeSensitivityReceipt(True, fill.fill_sha256, digest, notional, brokerage, stt,
                                 exchange, sebi, gst, stamp, extra, total, ())
