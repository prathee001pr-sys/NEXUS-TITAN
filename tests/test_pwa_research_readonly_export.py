"""NEXUS TITAN owner-only PWA integration prerequisite, not a deployed API."""
from dataclasses import replace
import copy
import hashlib
import json

import pytest

from nexus_titan.dashboard.pwa_research_export import (
    export_local_pwa_research_status, validate_local_pwa_research_status,
)
from nexus_titan.operations.stage145_dashboard_status import DashboardResearchStatus


def status(market="INDIAN_FO", *, eligible=True, reasons=None):
    if reasons is None:
        reasons = () if eligible else ("UNVERIFIED_LOCAL_RESEARCH_ONLY",)
    return DashboardResearchStatus(
        market=market,
        research_status="HUMAN_REVIEW" if eligible else "BLOCKED",
        research_review_eligible=eligible,
        human_review_required=True,
        live_trading_enabled=False,
        automatic_promotion_enabled=False,
        reasons=reasons,
    )


def export(india=True, crypto=False):
    return export_local_pwa_research_status(
        status(eligible=india), status("CRYPTO", eligible=crypto),
    )


def test_local_read_only_export_is_bounded_deterministic_json():
    packet=export()
    assert packet==export()
    assert validate_local_pwa_research_status(packet)
    raw=json.dumps(packet)
    assert len(raw.encode()) <= 4096
    assert validate_local_pwa_research_status(json.loads(raw))
    assert packet["markets"]["INDIAN_FO"]["status"]=="RESEARCH_REVIEW_ONLY"
    assert packet["markets"]["CRYPTO"]["status"]=="BLOCKED"
    assert packet["source_commit_verified"] is False
    assert packet["transport_owner_auth_verified"] is False
    assert packet["independently_verified_records"] == 0
    assert not any(packet["safety"].values())


def test_pwa_export_does_not_copy_user_untrusted_reasons_or_secret_material():
    bait="PERSONAL_TOKEN_ABCD1234_SECRETS_DO_NOT_EXPOSE"
    blocked=status(eligible=False, reasons=(bait,))
    packet=export_local_pwa_research_status(blocked,status("CRYPTO"))
    raw=json.dumps(packet)
    assert bait not in raw
    assert "order_id" not in raw
    assert "account_id" not in raw
    assert "token" not in raw.lower()
    assert validate_local_pwa_research_status(packet)


@pytest.mark.parametrize("which",["live_trading_enabled",
    "automatic_promotion_enabled","human_review_required"])
def test_privileged_stage145_receipts_rejected(which):
    normal=status()
    changed=replace(normal,**{which:False if which=="human_review_required" else True})
    with pytest.raises(ValueError):
        export_local_pwa_research_status(changed,status("CRYPTO"))


@pytest.mark.parametrize("field",[
    "owner_identity_authenticated",
    "pwa_session_authenticated",
    "github_status_independently_verified",
    "live_trading_authorized",
    "production_ready",
    "independent_global_risk_veto_verified",
])
def test_spoofed_privilege_rejected_even_with_rehashed_packet(field):
    packet=export()
    packet["safety"][field]=True
    contents={k:v for k,v in packet.items() if k!="content_sha256"}
    packet["content_sha256"]=hashlib.sha256(
        json.dumps(contents,sort_keys=True,separators=(",",":"),
                   ensure_ascii=True,allow_nan=False).encode("ascii")
    ).hexdigest()
    assert not validate_local_pwa_research_status(packet)


def test_false_like_zero_never_replaces_explicit_false():
    packet=export()
    packet["safety"]["production_ready"]=0
    assert not validate_local_pwa_research_status(packet)


def test_digest_detects_accidental_mutation():
    packet=export()
    packet["markets"]["CRYPTO"]["eligible_for_local_human_research_review"]=True
    assert not validate_local_pwa_research_status(packet)


def test_market_swapping_and_conflicting_status_fail_closed():
    with pytest.raises(ValueError):
        export_local_pwa_research_status(status("CRYPTO"),status())
    with pytest.raises(ValueError):
        export_local_pwa_research_status(
            replace(status(),research_status="BLOCKED"),status("CRYPTO"))
    with pytest.raises(TypeError):
        export_local_pwa_research_status(None,status("CRYPTO"))


def test_json_extra_keys_and_recomputed_digest_do_not_authorize():
    packet=copy.deepcopy(export())
    packet["safety"]["live_trading_authorized"]="false"
    assert not validate_local_pwa_research_status(packet)
    packet=export()
    packet["remote_owner_token"]="secret"
    assert not validate_local_pwa_research_status(packet)


def test_export_never_forges_unaudited_real_data_for_both_markets():
    packet=export(india=False,crypto=False)
    assert validate_local_pwa_research_status(packet)
    assert all(x["status"]=="BLOCKED" for x in packet["markets"].values())
    assert "real_market_data_authenticity_unverified" in packet["fixed_release_gaps"]
    assert packet["safety"]["paper_order_submission_authorized"] is False
