"""Stage 197: multiple additional execution-cost sensitivities, synthetic only.

These amounts are assumptions; no inference about historical spreads or fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

from .stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from .stage193_cost_stress import audit_extra_cost_stress

_NAME = re.compile(r'[a-z][a-z0-9_-]{0,39}\Z')


@dataclass(frozen=True, slots=True)
class FrictionScenario:
    name: str
    extra_cost_per_roundtrip: str
    max_acceptable_loss: str


@dataclass(frozen=True, slots=True)
class FrictionGridReceipt:
    accepted: bool
    ledger_sha256: str
    worst_stressed_net_pnl: Decimal | None
    scenario_sha256: str
    blockers: tuple[str, ...]


def audit_friction_scenario_grid(trades: tuple[ClosedReplay, ...],
                                 scenarios: tuple[FrictionScenario, ...]) -> FrictionGridReceipt:
    if not isinstance(scenarios, tuple) or not 2 <= len(scenarios) <= 32:
        return FrictionGridReceipt(False, '', None, '', ('2–32 scenarios required',))
    ledger = audit_portfolio_replay_ledger(trades)
    if not ledger.accepted:
        return FrictionGridReceipt(False, '', None, '', ('invalid Stage 191 ledger',))
    names: set[str] = set()
    worst: Decimal | None = None
    canonical: list[dict[str, str]] = []
    for i, scenario in enumerate(scenarios):
        if (type(scenario) is not FrictionScenario or not isinstance(scenario.name, str)
                or not _NAME.fullmatch(scenario.name) or scenario.name in names):
            return FrictionGridReceipt(False, ledger.ledger_sha256, None, '',
                                       (f'scenario {i}: duplicate/invalid scenario',))
        names.add(scenario.name)
        checked = audit_extra_cost_stress(
            trades, ledger=ledger, extra_cost_per_roundtrip=scenario.extra_cost_per_roundtrip,
            max_acceptable_loss=scenario.max_acceptable_loss)
        if not checked.accepted or type(checked.stressed_net_pnl) is not Decimal or not checked.stressed_net_pnl.is_finite():
            return FrictionGridReceipt(False, ledger.ledger_sha256, None, '',
                                       (f'scenario {i}: cost stress rejected',))
        worst = (checked.stressed_net_pnl if worst is None else min(worst, checked.stressed_net_pnl))
        canonical.append({'name': scenario.name, 'cost_digest': checked.cost_sha256,
                          'net': str(checked.stressed_net_pnl)})
    raw = json.dumps({'ledger': ledger.ledger_sha256, 'scenarios': canonical},
                     sort_keys=True, separators=(',', ':'))
    return FrictionGridReceipt(True, ledger.ledger_sha256, worst,
                               hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
