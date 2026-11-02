"""Stage32 offline safety-preflight smoke: new synthetic flat paper accounts only.

Not a live order / broker process. Existing user data and accounts untouched.
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from nexus_titan.shadow.paper_safety_preflight import inspect_paper_safety_preflight
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import VirtualAccount, TradingMode


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="titan-stage32-synthetic-") as location:
        base=Path(location)
        virtual=VirtualAccount(
            "STAGE32-OFFLINE",starting_capital=50000,
            require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
            approval_authorizer=lambda actor,resource: actor=="SYNTHETIC-ONLY",
            state_dir=base/"virtual",
        )
        research=DurableResearchShadowLedger(
            base/"research.sqlite3",account_id="STAGE32-OFFLINE",
            starting_capital=50000,guarded_paper_mode=True,
        )
        outcome=inspect_paper_safety_preflight(virtual,research)
        print(json.dumps(asdict(outcome),indent=2,sort_keys=True))
        return 0 if outcome.flat_research_gate_passed else 2


if __name__=="__main__":
    raise SystemExit(main())
