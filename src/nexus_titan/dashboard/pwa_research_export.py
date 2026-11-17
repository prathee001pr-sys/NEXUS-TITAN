"""Owner-only PWA *transport candidate*: local, bounded, read-only research status.

This module cannot authenticate an owner, contact GitHub, launch a server,
read credentials, or authorize broker/paper actions. The SHA digest only
detects accidental changes; it is NOT a signature or identity assertion.
"""
from __future__ import annotations

import hashlib
import json

from nexus_titan.operations.stage145_dashboard_status import DashboardResearchStatus
from nexus_titan.operations.stage148_readiness_report import generate_readiness_report


SCHEMA = "NEXUS_TITAN_PWA_LOCAL_RESEARCH_EXPORT_V1"
_NO_GO = {
    "owner_identity_authenticated": False,
    "pwa_session_authenticated": False,
    "github_status_independently_verified": False,
    "independent_global_risk_veto_verified": False,
    "real_market_data_authenticated": False,
    "live_trading_authorized": False,
    "automatic_strategy_promotion_authorized": False,
    "production_ready": False,
    "paper_order_submission_authorized": False,
}
_EXPECTED_GAPS = (
    "real_market_data_authenticity_unverified",
    "out_of_sample_validation_not_established",
    "realistic_broker_execution_not_verified",
    "independent_security_audit_incomplete",
    "production_operational_readiness_unverified",
)
_MARKETS = ("INDIAN_FO", "CRYPTO")


def _canon(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def export_local_pwa_research_status(
    indian_fo: DashboardResearchStatus,
    crypto: DashboardResearchStatus,
) -> dict[str, object]:
    """Return a JSON-safe display packet without untrusted raw evidence fields.

    No account IDs, live account values, external URLs, secrets, order handles,
    custom reason texts, operator-supplied GitHub labels or timestamps included.
    """
    if type(indian_fo) is not DashboardResearchStatus or type(crypto) is not DashboardResearchStatus:
        raise TypeError("Two explicit Stage145 dashboard status receipts required")
    if indian_fo.market != "INDIAN_FO" or crypto.market != "CRYPTO":
        raise ValueError("Market-specific receipt identity mismatch")
    models = (generate_readiness_report(indian_fo),
              generate_readiness_report(crypto))
    rows: dict[str, object] = {}
    for market, report in zip(_MARKETS, models):
        # Stage148 validates all privilege and consistency flags. Its gap
        # descriptions must not become a raw reason/secret/PII transport.
        if (type(report.research_review_eligible) is not bool
                or report.production_ready is not False
                or report.live_authorized is not False
                or report.human_review_required is not True
                or not all(g in report.outstanding_gaps for g in _EXPECTED_GAPS)
                or report.status not in ("BLOCKED", "RESEARCH_REVIEW_ONLY")):
            raise ValueError("Invalid or privileged research readiness")
        rows[market] = {
            "status": report.status,
            "eligible_for_local_human_research_review": report.research_review_eligible,
            "human_review_required": True,
            "source": "STAGE145_LOCAL_UNVERIFIED_RESEARCH",
        }
    packet: dict[str, object] = {
        "schema": SCHEMA,
        "scope": "DISPLAY_ONLY_LOCAL_RESEARCH_NO_GO",
        "markets": rows,
        "fixed_release_gaps": list(_EXPECTED_GAPS),
        "safety": dict(_NO_GO),
        "independently_verified_records": 0,
        "source_commit_verified": False,
        "transport_owner_auth_verified": False,
    }
    packet["content_sha256"] = _digest(packet)
    if len(_canon(packet)) > 4096:
        raise ValueError("PWA research export exceeds bounded packet size")
    return packet


def validate_local_pwa_research_status(packet: object) -> bool:
    """Check local packet shape and integrity, NOT ownership/authenticity."""
    if type(packet) is not dict or set(packet) != {
        "schema", "scope", "markets", "fixed_release_gaps", "safety",
        "independently_verified_records", "source_commit_verified",
        "transport_owner_auth_verified", "content_sha256",
    }:
        return False
    if packet["schema"] != SCHEMA or packet["scope"] != "DISPLAY_ONLY_LOCAL_RESEARCH_NO_GO":
        return False
    if (type(packet["markets"]) is not dict
            or set(packet["markets"]) != set(_MARKETS)
            or type(packet["fixed_release_gaps"]) is not list
            or packet["fixed_release_gaps"] != list(_EXPECTED_GAPS)
            or type(packet["safety"]) is not dict
            or packet["safety"] != _NO_GO
            or any(type(v) is not bool or v is not False for v in packet["safety"].values())
            or type(packet["independently_verified_records"]) is not int
            or packet["independently_verified_records"] != 0
            or packet["source_commit_verified"] is not False
            or packet["transport_owner_auth_verified"] is not False):
        return False
    for m in _MARKETS:
        row = packet["markets"][m]
        if (type(row) is not dict
                or set(row) != {"status", "eligible_for_local_human_research_review",
                               "human_review_required", "source"}
                or row["source"] != "STAGE145_LOCAL_UNVERIFIED_RESEARCH"
                or row["human_review_required"] is not True
                or type(row["eligible_for_local_human_research_review"]) is not bool
                or row["status"] != ("RESEARCH_REVIEW_ONLY"
                   if row["eligible_for_local_human_research_review"] else "BLOCKED")):
            return False
    try:
        raw_hash = packet["content_sha256"]
        if type(raw_hash) is not str or len(raw_hash) != 64:
            return False
        plain = {k: v for k, v in packet.items() if k != "content_sha256"}
        return (raw_hash == _digest(plain)
                and len(_canon(packet)) <= 4096)
    except (TypeError, ValueError, OverflowError, UnicodeError):
        return False
