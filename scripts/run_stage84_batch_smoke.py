"""Stage84 sequential 81-84 batch local research smoke; no broker/market data."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus_titan.operations.stage81_root_ancestry_review import inspect_stage81_candidate
from nexus_titan.operations.isolated_atomic_execution_book import Stage55IsolatedSyntheticExecutionBook

ROOT=Path(__file__).resolve().parents[1]
def main():
    evidence=json.loads((ROOT/"docs/STAGE81_TWO_ROOT_ANCESTRY_EVIDENCE_2026-11-04.json").read_text())
    ancestry=inspect_stage81_candidate(ROOT,evidence)
    with TemporaryDirectory(prefix="titan-stage84-") as directory:
        book=Stage55IsolatedSyntheticExecutionBook(
            db_path=Path(directory)/"single.db",
            account_id="stage84-demo",starting_cents=100000,
        )
        snap=book.snapshot_local_synthetic_portfolio()
        output={
            "mode":"STAGE84_BATCH_81_84_SYNTHETIC_NO_GO",
            "two_dev_ancestor_roots_locally_present":ancestry.root_prs_present_in_development_history== (1,3),
            "stage83_local_ledger_integrity":snap.local_integrity_verified,
            "local_kill_state_available":snap.kill_switch_active is False,
            "real_market_feed_verified":False,"global_risk_capital_authority":False,
            "main_merge_authorized":False,"paper_order_authorized":False,
            "live_trading_enabled":False,"broker_orders_transmitted":0,
            "verdict":"STAGE84_BATCH_INTEGRATION_SYNTHETIC_ONLY_NO_GO",
        }
        print(json.dumps(output,indent=2,sort_keys=True))
        return 0 if (output["two_dev_ancestor_roots_locally_present"]
                     and output["stage83_local_ledger_integrity"]
                     and not output["live_trading_enabled"]) else 2
if __name__=="__main__":raise SystemExit(main())
