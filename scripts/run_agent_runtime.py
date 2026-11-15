"""Run a human-approved ACE agent workflow using safe local adapters.

Example:
  PYTHONPATH=src python scripts/run_agent_runtime.py --db data/titan_learning.db --workflow examples/agent_workflow.sample.json

No approval is granted by this script. Agent specifications must already have
been reviewed and be present in the permanent registry.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.self_improvement import (  # noqa: E402
    AgentRuntime, AgentWorkflowCoordinator, LearningStore, TitanEvolveEngine,
    register_core_local_tools,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="TITAN controlled specialist-agent runtime")
    parser.add_argument("--db", default=str(ROOT / "data" / "titan_learning.db"),
                        help="ACE + learning + runtime SQLite database")
    parser.add_argument("--workflow", help="JSON workflow file. Must target human-approved agents only.")
    parser.add_argument("--show-metrics", action="store_true", help="Print measured per-agent runtime metrics.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    store = LearningStore(db_path)
    engine = TitanEvolveEngine(store)
    runtime = AgentRuntime(db_path)
    available = register_core_local_tools(runtime, engine)
    print("Registered safe local adapters:", ", ".join(available))

    if args.workflow:
        workflow_path = Path(args.workflow).resolve()
        try:
            payload = json.loads(workflow_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
                raise ValueError("Workflow JSON must contain a tasks array.")
            result = AgentWorkflowCoordinator(runtime).execute_workflow(
                payload["tasks"], workflow_id=payload.get("workflow_id"))
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            if result["status"] != "COMPLETED":
                return 2
        except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            print(f"Workflow rejected or failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    if args.show_metrics:
        print(json.dumps(runtime.metrics(), indent=2, ensure_ascii=False))
    if not args.workflow and not args.show_metrics:
        parser.print_help()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
