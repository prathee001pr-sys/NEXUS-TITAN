"""Stage82 local SQLite kill-switch no-input synthetic smoke."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,Stage55SyntheticBookBlocked,
)
def main():
    with tempfile.TemporaryDirectory(prefix="titan-82-") as p:
        a=Stage55IsolatedSyntheticExecutionBook(
            db_path=Path(p)/"ledger.sqlite",account_id="stage82-smoke",starting_cents=100000,
        )
        a.set_local_synthetic_kill_switch(active=True,operation_id="stop")
        stopped=False
        try:
            a.reserve_synthetic_buy(request_id="blocked",symbol="NIFTYOPT",
                                    quantity=1,limit_price_cents=500,fee_buffer_cents=0)
        except Stage55SyntheticBookBlocked:
            stopped=True
        report={"mode":"STAGE82_LOCAL_SQLITE_STOP_ONLY",
                "raw_direct_same_file_order_denied":stopped,
                "same_db_integrity_verified":a.inspect().local_integrity_verified,
                "globally_unbypassable_risk_veto":False,
                "independent_risk_authentication":False,
                "cross_ledger_capital_integrated":False,
                "paper_order_authorized":False,"live_trading_enabled":False,
                "broker_orders_transmitted":0,
                "verdict":"STAGE82_LOCAL_SQLITE_KILL_ONLY_NO_GO"}
        print(json.dumps(report,sort_keys=True,indent=2))
        return 0 if stopped and a.inspect().revision==0 else 2
if __name__=="__main__":raise SystemExit(main())
