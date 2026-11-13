"""Stage 200: combined OFFLINE SYNTHETIC review gate, categorically NO-GO for live.

Even an accepted result can never authorize orders, deployment or promotion.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json

from .stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from .stage196_integrated_synthetic_audit import SyntheticAuditPolicy, audit_integrated_synthetic_portfolio
from .stage197_friction_scenario_grid import FrictionScenario, audit_friction_scenario_grid
from .stage198_replay_stability import audit_replay_stability
from .stage199_integrity_recheck import SyntheticIntegrityReceipt, audit_integrated_integrity


@dataclass(frozen=True, slots=True)
class SyntheticNoGoReceipt:
    eligible_for_offline_synthetic_review: bool
    synthetic_evidence_sha256: str
    blockers: tuple[str, ...]
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_stage200_no_go(
    trades: tuple[ClosedReplay, ...], *, policy: SyntheticAuditPolicy,
    scenarios: tuple[FrictionScenario, ...], evidence: SyntheticIntegrityReceipt,
    provenance_attested: bool, independent_risk_veto_attested: bool,
    holdout_separation_attested: bool, independent_review_attested: bool,
    live_requested: bool = False, autonomous_requested: bool = False,
    promotion_requested: bool = False,
) -> SyntheticNoGoReceipt:
    errors = []
    if live_requested is not False or autonomous_requested is not False or promotion_requested is not False:
        errors.append('live/autonomous/promotion prohibited')
    if independent_review_attested is not True:
        errors.append('independent synthetic review attestation required')
    if errors:
        return SyntheticNoGoReceipt(False, '', tuple(errors))
    pipeline = audit_integrated_synthetic_portfolio(
        trades, policy=policy, provenance_attested=provenance_attested,
        independent_risk_veto_attested=independent_risk_veto_attested,
        holdout_separation_attested=holdout_separation_attested)
    friction = audit_friction_scenario_grid(trades, scenarios)
    replay = audit_replay_stability(trades, ledger=audit_portfolio_replay_ledger(trades))
    checked = audit_integrated_integrity(
        trades, policy=policy, scenarios=scenarios, pipeline=pipeline,
        friction=friction, replay=replay, provenance_attested=provenance_attested,
        independent_risk_veto_attested=independent_risk_veto_attested,
        holdout_separation_attested=holdout_separation_attested)
    if type(evidence) is not SyntheticIntegrityReceipt or not checked.accepted or evidence != checked:
        return SyntheticNoGoReceipt(False, '', ('unlinked or rejected Stage 199 evidence',))
    raw = json.dumps({'integrity': checked.evidence_sha256, 'mode': 'offline_synthetic_only'},
                     sort_keys=True, separators=(',', ':'))
    return SyntheticNoGoReceipt(True, hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
