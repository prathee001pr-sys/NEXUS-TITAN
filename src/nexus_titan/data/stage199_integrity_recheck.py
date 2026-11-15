"""Stage 199: re-run the pipeline and stress evidence to block forged receipts."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json

from .stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from .stage196_integrated_synthetic_audit import (
    SyntheticAuditPolicy, IntegratedSyntheticReceipt, audit_integrated_synthetic_portfolio,
)
from .stage197_friction_scenario_grid import (
    FrictionScenario, FrictionGridReceipt, audit_friction_scenario_grid,
)
from .stage198_replay_stability import ReplayStabilityReceipt, audit_replay_stability


@dataclass(frozen=True, slots=True)
class SyntheticIntegrityReceipt:
    accepted: bool
    evidence_sha256: str
    blockers: tuple[str, ...]


def audit_integrated_integrity(
    trades: tuple[ClosedReplay, ...], *, policy: SyntheticAuditPolicy,
    scenarios: tuple[FrictionScenario, ...], pipeline: IntegratedSyntheticReceipt,
    friction: FrictionGridReceipt, replay: ReplayStabilityReceipt,
    provenance_attested: bool, independent_risk_veto_attested: bool,
    holdout_separation_attested: bool,
) -> SyntheticIntegrityReceipt:
    """Independently reconstruct all inputs and equality-compare immutable receipts."""
    checked_pipeline = audit_integrated_synthetic_portfolio(
        trades, policy=policy, provenance_attested=provenance_attested,
        independent_risk_veto_attested=independent_risk_veto_attested,
        holdout_separation_attested=holdout_separation_attested)
    checked_friction = audit_friction_scenario_grid(trades, scenarios)
    ledger = audit_portfolio_replay_ledger(trades)
    checked_replay = audit_replay_stability(trades, ledger=ledger)
    errors = []
    if (type(pipeline) is not IntegratedSyntheticReceipt or pipeline != checked_pipeline
            or not checked_pipeline.accepted_for_synthetic_review):
        errors.append('Stage 196 pipeline or evidence mismatch')
    if (type(friction) is not FrictionGridReceipt or friction != checked_friction
            or not checked_friction.accepted):
        errors.append('Stage 197 friction grid mismatch')
    if (type(replay) is not ReplayStabilityReceipt or replay != checked_replay
            or not checked_replay.accepted):
        errors.append('Stage 198 replay stability mismatch')
    if errors:
        return SyntheticIntegrityReceipt(False, '', tuple(errors))
    raw = json.dumps({'pipeline': pipeline.evidence_sha256,
                      'friction': friction.scenario_sha256,
                      'replay': replay.replay_stability_sha256},
                     sort_keys=True, separators=(',', ':'))
    return SyntheticIntegrityReceipt(True, hashlib.sha256(raw.encode('ascii')).hexdigest(), ())
