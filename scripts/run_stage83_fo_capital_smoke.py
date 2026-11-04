"""Stage83 read-only local portfolio snapshot smoke; synthetic only."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus_titan.operations.isolated_atomic_execution_book import Stage55IsolatedSyntheticExecutionBook

def main():
    with TemporaryDirectory(prefix="titan-83-") as directory:
        b=Stage55IsolatedSyntheticExecutionBook(
            db_path=Path(directory)/"one.sqlite", account_id="test-only",
            starting_cents=100000,
        )
        s=b.snapshot_local_synthetic_portfolio()
        print(json.dumps({
            "mode":"STAGE83_ONE_SQLITE_FO_RECONCILIATION_RESEARCH",
            "single_db_replay_ok":s.local_integrity_verified,
            "empty_capital_unchanged":s.cash_cents==100000 and s.reserved_cents==0,
            "global_capital_authority_verified":False,
            "paper_order_authorized":False,"live_trading_enabled":False,
            "broker_orders_transmitted":0,
            "verdict":"STAGE83_SINGLE_SQLITE_FO_ACCOUNT_RESEARCH_NO_GO",
        },indent=2,sort_keys=True))
        return 0 if s.local_integrity_verified and s.available_cents==100000 else 2
if __name__=="__main__":raise SystemExit(main())
