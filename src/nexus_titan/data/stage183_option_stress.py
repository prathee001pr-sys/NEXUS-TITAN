"""Stage 183: explicit user-supplied multi-leg option mark stress, offline only.

This is a scenario *sampling* audit, not a maximum possible loss guarantee,
VaR estimate, option-pricing model, or exchange-cleared margin estimate.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from .stage176_quote_sanity import parse_amount
from .stage182_option_legs import OptionLeg, OptionLegReceipt, audit_option_legs


@dataclass(frozen=True, slots=True)
class OptionStressReceipt:
    accepted: bool
    worst_scenario_loss: Decimal | None
    scenario_count: int
    legs_sha256: str
    blockers: tuple[str, ...]


def audit_option_stress(legs: tuple[OptionLeg, ...], *, asof: date,
                        exposure: OptionLegReceipt,
                        scenario_marks: tuple[tuple[str, ...], ...],
                        scenario_costs: tuple[str, ...],
                        max_sampled_loss: str,
                        marks_verified: bool, costs_verified: bool,
                        lot_size_verified: bool) -> OptionStressReceipt:
    blockers = []
    canonical = audit_option_legs(legs, asof=asof, lot_size_verified=lot_size_verified)
    if (not isinstance(exposure, OptionLegReceipt) or not exposure.accepted
            or not canonical.accepted or exposure != canonical):
        blockers.append('unverified or mismatched option legs')
    if marks_verified is not True or costs_verified is not True:
        blockers.append('unverified scenario marks or costs')
    if (not isinstance(scenario_marks, tuple) or not 1 <= len(scenario_marks) <= 64
            or not isinstance(scenario_costs, tuple) or len(scenario_costs) != len(scenario_marks)):
        return OptionStressReceipt(False, None, 0, '', tuple(blockers + ['invalid scenario count']))
    try:
        cap = parse_amount(max_sampled_loss)
    except ValueError:
        return OptionStressReceipt(False, None, len(scenario_marks), '', tuple(blockers + ['invalid loss cap']))
    if cap <= 0:
        blockers.append('nonpositive loss cap')
    worst_loss = Decimal('0')
    for idx, (marks, cost_str) in enumerate(zip(scenario_marks, scenario_costs)):
        try:
            if not isinstance(marks, tuple) or len(marks) != len(legs):
                raise ValueError('wrong leg count')
            cost = parse_amount(cost_str)
            pnl = -cost
            for leg, mark_str in zip(legs, marks):
                if not isinstance(leg, OptionLeg):
                    raise ValueError('invalid leg')
                mark = parse_amount(mark_str)
                entry = parse_amount(leg.entry_premium)
                movement = (mark - entry) * leg.lot_size * leg.lots
                pnl += movement if leg.side == 'BUY' else -movement
            worst_loss = max(worst_loss, -pnl)
        except (ValueError, TypeError, OverflowError):
            blockers.append(f'scenario {idx}: malformed marks or costs')
            break
    if worst_loss > cap:
        blockers.append('sampled scenario loss exceeds bound')
    return OptionStressReceipt(not blockers, worst_loss if not any('malformed' in b for b in blockers) else None,
                               len(scenario_marks), canonical.legs_sha256 if canonical.accepted and exposure == canonical else '',
                               tuple(blockers[:24]))
