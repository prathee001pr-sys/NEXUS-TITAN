"""Stage73 empty-memory F&O EVOLVE safety smoke: no market I/O, code fit or trade."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.evolve.stage73_fo_experience import Stage73FOExperienceMemory


def main() -> int:
    memory = Stage73FOExperienceMemory()
    report = memory.compare(champion="baseline", challenger="challenger")
    packet = {
        "mode": "STAGE73_EMPTY_EXPERIENCE_RESEARCH_QA",
        "paired_resolved_episodes": report.paired_count,
        "journal_integrity_local": memory.verify_local_integrity(),
        "independently_authenticated_labels": report.independently_verified_outcomes,
        "persistent_experience_storage": False,
        "model_weights_updated": report.model_weights_updated,
        "strategy_promotion_authorized": report.strategy_promotion_authorized,
        "live_trading_enabled": report.live_trading_enabled,
        "broker_orders_transmitted": report.broker_orders_transmitted,
        "verdict": report.verdict,
    }
    print(json.dumps(packet, sort_keys=True, indent=2, allow_nan=False))
    return 0 if (
        packet["journal_integrity_local"] and packet["paired_resolved_episodes"] == 0
        and not packet["live_trading_enabled"]
        and not packet["strategy_promotion_authorized"]
        and not packet["model_weights_updated"]
        and packet["broker_orders_transmitted"] == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
