"""One-shot TITAN EVOLVE scheduled research worker.

Register a source:
  PYTHONPATH=src python scripts/run_evolve_scheduler.py --db data/titan_evolve.db \
    --allow-hosts docs.python.org --add-source https://docs.python.org/3/library/asyncio.html

Run due sources (suitable for a Replit Scheduled Deployment / cron):
  PYTHONPATH=src python scripts/run_evolve_scheduler.py --db data/titan_evolve.db \
    --allow-hosts docs.python.org --run-due

List stored sources:
  PYTHONPATH=src python scripts/run_evolve_scheduler.py --db data/titan_evolve.db --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.self_improvement import (
    AllowlistedHTTPSResearchSource,
    LearningStore,
    ResearchScheduleStore,
    ScheduledResearchWorker,
    TitanEvolveEngine,
    OpenAICompatibleProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="TITAN EVOLVE persistent scheduled research worker")
    parser.add_argument("--db", default=str(ROOT / "data" / "titan_evolve_runtime.db"))
    parser.add_argument("--allow-hosts", default="",
                        help="Comma-separated exact hostnames permitted for HTTPS fetching.")
    parser.add_argument("--add-source", default=None, help="Register an HTTPS research URL.")
    parser.add_argument("--topic", default="scheduled-research")
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--run-due", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--max-sources", type=int, default=20)
    args = parser.parse_args()

    hosts = {h.strip().lower().rstrip(".") for h in args.allow_hosts.split(",") if h.strip()}
    engine = TitanEvolveEngine(LearningStore(args.db))
    schedule = ResearchScheduleStore(engine.store.db_path)

    if args.add_source:
        if not hosts:
            parser.error("--add-source requires --allow-hosts with the exact URL hostname.")
        host = urlsplit(args.add_source).hostname
        if not host or host.lower().rstrip(".") not in hosts:
            parser.error("The --add-source hostname must exactly match one of --allow-hosts.")
        if not 300 <= args.interval_hours * 3600 <= 31 * 86400:
            parser.error("--interval-hours must be between 5 minutes and 31 days.")
        item = schedule.register_source(
            args.add_source, topic=args.topic,
            interval_seconds=int(args.interval_hours * 3600),
            run_immediately=True,
        )
        print("Registered source:", json.dumps(item.__dict__, indent=2))

    if args.list:
        print(json.dumps([item.__dict__ for item in schedule.list_sources()], indent=2))
        print("Stats:", json.dumps(schedule.stats(), sort_keys=True))
        return 0

    if args.run_due:
        if not hosts:
            parser.error("--run-due requires --allow-hosts; no network host is implicitly trusted.")
        fetcher = AllowlistedHTTPSResearchSource(hosts)
        worker = ScheduledResearchWorker(
            engine, fetcher, llm_provider=OpenAICompatibleProvider.from_environment()
        )
        results = worker.run_due(limit=args.max_sources)
        for result in results:
            print(json.dumps(result.to_dict(), ensure_ascii=False))
        print("Scheduler stats:", json.dumps(schedule.stats(), sort_keys=True))
        return 1 if any(result.status == "ERROR" for result in results) else 0

    if not args.add_source:
        parser.print_help()
        print("\nNo research fetch was run. Use --add-source to register an exact URL and --run-due to fetch due sources.")
    print("Scheduler stats:", json.dumps(schedule.stats(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
