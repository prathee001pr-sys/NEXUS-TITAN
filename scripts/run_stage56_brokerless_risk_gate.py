"""Stage56 one-shot JSON stdin risk/veto subprocess — no broker or order API.

Contract: exactly ONE <=16 KiB JSON document, schema_version=1, fixed QA
risk policy. Output only an untrusted local screening result. This service
has NO access to exchange credentials, broker SDKs, internet, order tables,
capital stores or approval tokens. Running in another Python subprocess
does not itself create an independently protected security boundary.

Usage:
    python scripts/run_stage56_brokerless_risk_gate.py < qa_request.json
The caller must never interpret a locally passing screen as an order grant.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.brokerless_risk_veto import (
    Stage56SyntheticIntent, Stage56SyntheticQuote,
    Stage56SyntheticRiskState, inspect_stage56_synthetic_risk,
)

_MAX_INPUT = 16_384

_INTENT_FIELDS = frozenset({
    "request_id", "symbol", "quantity", "limit_price_cents",
    "stop_price_cents", "fee_buffer_cents", "instrument_type", "side",
})
_QUOTE_FIELDS = frozenset({
    "observed_at", "bid_cents", "ask_cents", "ask_depth_units",
    "expected_slippage_bps", "expected_edge_bps", "source_reference",
})
_ACCOUNT_FIELDS = frozenset({
    "account_id", "initial_cents", "available_cents", "already_reserved_cents",
    "daily_realized_loss_bps", "current_drawdown_bps", "consecutive_losses",
    "kill_switch_active", "risk_module_healthy",
})


def _exact_dict(value: object, keys: frozenset[str], kind: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Invalid/missing/extra " + kind + " keys")
    return value


def _deny_json(reason: str) -> dict:
    # Do not echo unsafe user-provided bytes, account identifiers or secrets.
    return {
        "schema_version": 1,
        "local_synthetic_screen_passed": False,
        "blockers": ["MALFORMED_OR_UNSUPPORTED_LOCAL_QA_REQUEST"],
        "message": reason,
        "order_submission_authorized": False,
        "synthetic_fill_authorized": False,
        "global_legacy_entrypoints_fenced": False,
        "trusted_risk_service_boundary_enforced": False,
        "external_quote_authenticated": False,
        "independent_human_identity_verified": False,
        "live_trading_enabled": False,
        "production_ready": False,
        "broker_orders_transmitted": 0,
    }


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT + 1)
        if not 0 < len(raw) <= _MAX_INPUT:
            raise ValueError("Input must be one nonempty JSON document <= 16 KiB")
        request = json.loads(raw.decode("utf-8"))
        _exact_dict(request, frozenset({
            "schema_version", "intent", "quote", "account",
        }), "top-level")
        if type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ValueError("Unsupported risk screening schema")
        intent_raw = _exact_dict(request["intent"], _INTENT_FIELDS, "intent")
        quote_raw = _exact_dict(request["quote"], _QUOTE_FIELDS, "quote")
        account_raw = _exact_dict(request["account"], _ACCOUNT_FIELDS, "account")
        when = quote_raw["observed_at"]
        if not isinstance(when, str) or len(when) > 48:
            raise ValueError("Quote time is invalid")
        quote = Stage56SyntheticQuote(
            **{**quote_raw, "observed_at": datetime.fromisoformat(when)},
        )
        intent = Stage56SyntheticIntent(**intent_raw)
        account = Stage56SyntheticRiskState(**account_raw)
        verdict = inspect_stage56_synthetic_risk(intent, quote, account)
        # Despite the success status below, this is NEVER a capability
        # token, account authorization or broker trade risk decision.
        data = asdict(verdict)
        data["risk_gate_kind"] = "BROKERLESS_LOCAL_SYNTHETIC_QA_ONLY"
        data["message"] = "Local caller-supplied screening ONLY; no order authorization"
        print(json.dumps(data, allow_nan=False, sort_keys=True))
        return 0
    except (UnicodeError, ValueError, TypeError, OverflowError, KeyError, json.JSONDecodeError):
        print(json.dumps(_deny_json("Rejected malformed local research JSON input"),
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
