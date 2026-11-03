"""Stage65 offline developer acceptance report; always PRODUCTION NO-GO.

Run: python scripts/run_stage65_final_acceptance.py
Uses a frozen historical GitHub PR snapshot and FABRICATED local market
data. No network/broker/account/live orders and no merge/PR mutation.
Exit 0 means local code/checklist smoke worked, NEVER release permission.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from nexus_titan.operations.integration_candidate_audit import inspect_stage62_candidate
from nexus_titan.operations.stage65_release_acceptance import (
    inspect_stage65_release_acceptance,
)
from nexus_titan.research.stage61_evidence_scorecard import inspect_stage61_fo_evidence
from nexus_titan.shadow.stage64_trial_governance import inspect_stage64_shadow_trial
from scripts.run_stage61_fo_evidence_smoke import _inputs
from scripts.run_stage64_shadow_trial_smoke import _trial, CAL

SNAPSHOT = ROOT / "docs/STAGE65_FINAL_PR_REVIEW_SNAPSHOT_2026-11-03.json"


def _market_report(
    root: Path, underlying: str, *, snapshot: dict, integration
) -> dict:
    h, oos, synthetic_execution = _inputs(root / underlying.lower(), underlying)
    evidence = inspect_stage61_fo_evidence(h, oos, execution=synthetic_execution)
    plan, days = _trial(underlying)
    trial = inspect_stage64_shadow_trial(
        plan, days, calendar=CAL,
        as_of=datetime.fromisoformat("2026-09-29T12:00:00+05:30"),
        fo_evidence=evidence, integration=integration,
    )
    result = inspect_stage65_release_acceptance(
        ROOT, pr_snapshot=snapshot, fo_evidence=evidence,
        trial=trial, integration=integration,
    )
    return {
        "scope": result.scope,
        "underlying": result.stage64_trial_underlying,
        "local_selected_code_checks": result.selected_source_and_ci_structural_review_passed,
        "local_synthetic_trial_criteria_met": result.stage64_local_trial_kpis_met,
        "operator_claimed_closed_trades": result.stage64_claimed_closed_trades,
        "observed_open_pr_count_at_snapshot": result.reviewed_open_pr_count,
        "root_pr_numbers": result.main_root_pr_numbers,
        "fully_listed_pr_diff_count": result.checked_pr_file_list_count,
        "pr_diff_lists_uninspected_count": result.uninspected_pr_file_list_count,
        "all_pr_changed_files_observed": result.all_pr_changed_files_observed,
        "independent_overlap_candidates": [
            {"pr_a": pair.pr_a, "pr_b": pair.pr_b, "paths": pair.paths}
            for pair in result.independent_file_overlap_candidates
        ],
        "reported_main_protected": result.reported_main_protected,
        "developer_offline_checklist_completed": result.developer_offline_checklist_completed,
        "local_evidence_digest_not_signed": result.acceptance_packet_sha256,
        "owner_actions": [
            {"id": action_id, "required": action}
            for action_id, action in result.required_owner_actions
        ],
        "release_blocker_count": result.critical_release_blocker_count,
        "release_verdict": result.release_verdict,
        "safe_to_merge": result.safe_to_merge,
        "production_ready": result.production_ready,
        "licensed_real_indian_fo_data_verified":
            result.licensed_real_indian_fo_data_verified,
        "real_shadow_trading_performance_verified":
            result.real_shadow_trading_performance_verified,
        "globally_unbypassable_risk_veto_verified":
            result.globally_unbypassable_risk_veto_verified,
        "one_authoritative_capital_authority_verified":
            result.single_atomic_capital_ledger_verified,
        "strategy_promotion_authorized": result.strategy_promotion_authorized,
        "real_money_trading_enabled": result.real_money_trading_enabled,
        "broker_orders_transmitted": result.broker_orders_transmitted,
    }


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    integration = inspect_stage62_candidate(ROOT, pr_snapshot=snapshot)
    with TemporaryDirectory(prefix="titan-stage65-no-trading-qa-") as folder:
        root = Path(folder)
        markets = {
            market.lower(): _market_report(
                root, market, snapshot=snapshot, integration=integration
            )
            for market in ("NIFTY", "BANKNIFTY")
        }
        packet = {
            "mode": "STAGE65_OFFLINE_FINAL_ACCEPTANCE_NO_GO_ONLY",
            "nifty": markets["nifty"],
            "banknifty": markets["banknifty"],
            "synthetic_untrusted_market_input_only": True,
            "frozen_pr_snapshot_not_live": True,
            "real_broker_data_or_identity_present": False,
            "merged_tree_ci_performed": False,
            "merges_performed": 0,
            "broker_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(packet, indent=2, sort_keys=True, allow_nan=False))
        return 0 if all((
            markets["nifty"]["developer_offline_checklist_completed"],
            markets["banknifty"]["developer_offline_checklist_completed"],
            markets["nifty"]["release_verdict"] ==
                "NO_GO_OWNER_AND_INDEPENDENT_EVIDENCE_REQUIRED",
            markets["banknifty"]["release_verdict"] ==
                "NO_GO_OWNER_AND_INDEPENDENT_EVIDENCE_REQUIRED",
            not packet["production_ready"],
            packet["broker_orders_transmitted"] == 0,
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
