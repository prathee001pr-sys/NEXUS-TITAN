"""Stage81 candidate root-ancestry NO-MERGE smoke, frozen data only."""
from __future__ import annotations
import json
import sys
from dataclasses import asdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from nexus_titan.operations.stage81_root_ancestry_review import inspect_stage81_candidate

def main():
    source=ROOT/"docs/STAGE81_TWO_ROOT_ANCESTRY_EVIDENCE_2026-11-04.json"
    review=inspect_stage81_candidate(ROOT,json.loads(source.read_text(encoding="utf-8")))
    print(json.dumps(asdict(review),sort_keys=True,indent=2))
    return 0 if (review.root_prs_present_in_development_history==(1,3)
                 and not review.merge_authorized and not review.live_trading_enabled
                 and review.broker_orders_transmitted==0) else 2

if __name__=="__main__":
    raise SystemExit(main())
