"""Read-only package dependency audit for the separately reviewed candidate."""
from dataclasses import asdict
import json
from pathlib import Path

from nexus_titan.operations.integration_candidate_audit import inspect_package_dependencies
from nexus_titan.operations.stage67_calibration_reconcile import inspect_stage67_calibration_reconciliation


def main():
    root = Path(__file__).resolve().parents[1]
    review = inspect_package_dependencies(root)
    lineage = inspect_stage67_calibration_reconciliation(root)
    print(json.dumps({"package": asdict(review), "lineage": asdict(lineage)}, sort_keys=True))
    return 0 if review.passed and lineage.frozen_source_lineage_check_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
