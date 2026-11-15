"""Stage43 offline, brokerless paper-only deployment smoke.

Writes ONLY to a temporary directory. It never reads uploaded market data,
exposes a web server, starts real-time workers or contacts a broker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentBlocked, PaperDeploymentConfig, open_paper_only_deployment,
)


def run_stage43_smoke() -> dict:
    with TemporaryDirectory(prefix="titan-stage43-offline-") as temp:
        root=Path(temp)
        common=dict(
            account_id="STAGE43-SYNTHETIC",starting_capital=50000,
            virtual_state_dir=root/"virtual",research_db_path=root/"research.sqlite3",
        )
        callback=lambda actor, order_id: actor=="SYNTHETIC-OWNER"
        locked=open_paper_only_deployment(
            PaperDeploymentConfig(**common),approval_authorizer=callback,
        )
        denied=False
        try:
            locked.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
        except PaperDeploymentBlocked:
            denied=True
        open_session=open_paper_only_deployment(
            PaperDeploymentConfig(**common,paper_orders_enabled=True),
            approval_authorizer=callback,
        )
        admitted=open_session.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
        )
        saved=open_session.virtual_account.orders[admitted.order_id]
        restart=open_paper_only_deployment(
            PaperDeploymentConfig(**common),approval_authorizer=callback,
        )
        status=restart.status()
        checks={
            "default_read_only":locked.status().read_only,
            "default_paper_buy_denied":denied,
            "manual_paper_buy_pending":admitted.status=="PENDING_APPROVAL",
            "no_unapproved_fills":saved.filled_qty==0,
            "gateway_only_durable":open_session.virtual_account.durable_store.gateway_only(
                open_session.virtual_account.account_id
            ),
            "strict_policy_durable":open_session.virtual_account.durable_store.strict_mode(
                open_session.virtual_account.account_id
            ),
            "restart_requires_fresh_opt_in":status.read_only,
            "pending_buy_survives_restart":admitted.order_id in restart.virtual_account.orders,
            "guarded_research_integrity":restart.research_ledger.verify_integrity(),
            "virtual_reconciliation":restart.virtual_account.reconcile().is_reconciled,
        }
        return {
            "stage":43,
            "mode":"TEMPORARY_SYNTHETIC_PAPER_ONLY",
            "checks":checks,
            "checks_passed":sum(checks.values()),
            "checks_total":len(checks),
            "all_checks_passed":all(checks.values()),
            "live_orders_transmitted":0,
            "real_market_data_verified":False,
            "global_legacy_apis_disabled":False,
            "externally_authenticated_identity":False,
            "cross_ledger_atomicity_verified":False,
            "production_ready":False,
        }


def main() -> int:
    result=run_stage43_smoke()
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["all_checks_passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
