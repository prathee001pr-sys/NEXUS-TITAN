"""Stage 220: fail-closed offline stage-progress evidence/recovery review gate.

No owner-only access, web endpoint, real market feed, GitHub signature or
production readiness is claimed. This is always NO-GO for live trading.
"""
from __future__ import annotations
from dataclasses import dataclass

from .stage215_evolve_no_go_gate import EvolveSafetyNoGoReceipt
from .stage216_progress_evidence import (StageProgressEvidence, StageEvidenceIntakeReceipt,
    audit_stage_progress_evidence, canonical_digest, sha_ok)
from .stage217_progress_journal import (ProgressEvent, ProgressJournalReceipt,
    audit_progress_journal)
from .stage218_dashboard_projection import (DashboardProjection,
    audit_dashboard_projection, project_offline_progress)
from .stage219_progress_backup import OfflineBackupReceipt, load_local_progress_snapshot


@dataclass(frozen=True, slots=True)
class OfflineProgressNoGoReceipt:
    eligible_for_local_read_only_progress_review: bool
    evidence_sha256: str
    blockers: tuple[str, ...]
    real_market_evidence_independently_verified: bool = False
    github_checks_independently_verified: bool = False
    owner_only_dashboard_access_verified: bool = False
    public_or_private_deployment_authorized: bool = False
    risk_limits_change_authorized: bool = False
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_offline_progress_no_go(*, baseline: object,
                                    evidence: object, intake: object,
                                    events: object, journal: object,
                                    dashboard: object, backup_path: object,
                                    live_requested: bool = False,
                                    autonomous_requested: bool = False,
                                    deployment_requested: bool = False,
                                    risk_change_requested: bool = False,
                                    promotion_requested: bool = False) -> OfflineProgressNoGoReceipt:
    checks = {
        'Stage215 typed synthetic-only research baseline': type(baseline) is EvolveSafetyNoGoReceipt
          and baseline.eligible_for_internal_offline_research_review is True and not baseline.blockers
          and sha_ok(baseline.evidence_sha256)
          and baseline.human_identity_independently_authenticated is False
          and baseline.external_market_data_authenticated is False
          and baseline.executable_changes_authorized is False
          and baseline.risk_limits_change_authorized is False
          and baseline.live_trading_authorized is False
          and baseline.autonomous_execution_authorized is False
          and baseline.strategy_promotion_authorized is False,
        'Stage216 evidence re-audited': type(evidence) is StageProgressEvidence
          and type(intake) is StageEvidenceIntakeReceipt
          and intake == audit_stage_progress_evidence(evidence)
          and intake.accepted_for_offline_progress_tracking is True
          and evidence.stage_number == 215,
        'Stage216 reported CI and scan success (unverified labels)': type(evidence) is StageProgressEvidence
          and evidence.github_ci_reported == 'success' and evidence.secret_scan_reported == 'success',
        'Stage217 journal re-audited': type(journal) is ProgressJournalReceipt
          and journal == audit_progress_journal(events)
          and journal.accepted is True,
        'Stage218 dashboard projection matches event replay': False,
        'Stage219 local snapshot reopen and matching projection': False,
        'Stage215 research hash linked to submitted progress evidence': False,
        'Stage216 evidence is latest journal event for Stage215': False,
        'live trading prohibited': live_requested is False,
        'autonomous execution prohibited': autonomous_requested is False,
        'deployment prohibited': deployment_requested is False,
        'risk changes prohibited': risk_change_requested is False,
        'strategy promotion prohibited': promotion_requested is False,
    }
    if checks['Stage215 typed synthetic-only research baseline'] and checks['Stage216 evidence re-audited']:
        checks['Stage215 research hash linked to submitted progress evidence'] = (
            evidence.linked_research_evidence_sha256 == baseline.evidence_sha256)
    if checks['Stage217 journal re-audited'] and checks['Stage216 evidence re-audited']:
        stage_events = [e for e in events if e.stage_number == 215]
        checks['Stage216 evidence is latest journal event for Stage215'] = bool(stage_events) and (
            stage_events[-1].evidence_sha256 == intake.evidence_sha256)
    if checks['Stage217 journal re-audited'] and type(dashboard) is DashboardProjection:
        try:
            recreated = project_offline_progress(events, stage_limit=dashboard.stage_limit)
            checks['Stage218 dashboard projection matches event replay'] = (
                dashboard == recreated and audit_dashboard_projection(dashboard) and dashboard.stage_limit == 220)
        except (TypeError, ValueError):
            pass
    if checks['Stage218 dashboard projection matches event replay']:
        restored, backup_receipt = load_local_progress_snapshot(backup_path)
        checks['Stage219 local snapshot reopen and matching projection'] = (
            restored == dashboard and backup_receipt.accepted and
            backup_receipt.independently_authenticated is False and
            backup_receipt.offsite_recovery_verified is False)
    blockers = tuple(name for name, passed in checks.items() if not passed)
    digest = canonical_digest({'stage215': baseline.evidence_sha256,
         'stage216': intake.evidence_sha256, 'stage217': journal.head_sha256,
         'stage218': dashboard.projection_sha256, 'scope': 'local_progress_read_only_NO_GO'}) if not blockers else ''
    return OfflineProgressNoGoReceipt(not blockers, digest, blockers)
