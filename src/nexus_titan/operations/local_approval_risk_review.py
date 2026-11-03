"""Stage57: read-only binding of Stage48 paper challenge to fresh Stage56 QA risk.

This optional local consistency review is NOT in the Stage48 signing or
VirtualAccount execution path. It cannot authenticate a real human, sign a
token, stop legacy API bypass, reserve cash, grant a BUY, or verify a broker.
The synthetic quote/account/clock are still caller-controlled. Full review
does not confer approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

from nexus_titan.operations.signed_paper_approval import Stage48ApprovalChallenge
from nexus_titan.operations.brokerless_risk_veto import (
    Stage56RiskPolicy, Stage56SyntheticIntent, Stage56SyntheticQuote,
    Stage56SyntheticRiskState, inspect_stage56_synthetic_risk,
)

_HEX64 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class Stage57ApprovalRiskReview:
    schema_version: int
    account_id: str
    paper_order_id: str
    local_consistency_observed: bool
    blockers: tuple[str, ...]
    order_snapshot_sha256: str | None
    risk_policy_sha256: str | None
    risk_input_sha256: str | None
    local_review_sha256: str | None
    local_risk_screen_passed: bool
    independent_human_identity_verified: bool = False
    external_market_quote_authenticated: bool = False
    signer_key_isolated_in_trusted_service: bool = False
    stage48_challenge_integrates_stage56_review: bool = False
    legacy_apis_globally_fenced: bool = False
    token_issue_authorized: bool = False
    order_submission_authorized: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False
    broker_orders_transmitted: int = 0


def inspect_stage57_local_approval_binding(
    challenge: Stage48ApprovalChallenge,
    intent: Stage56SyntheticIntent,
    quote: Stage56SyntheticQuote,
    account: Stage56SyntheticRiskState,
    *,
    expected_risk_policy_sha256: str,
    expected_risk_input_sha256: str,
    policy: Stage56RiskPolicy = Stage56RiskPolicy(),
    now: datetime | None = None,
) -> Stage57ApprovalRiskReview:
    """Re-run local synthetic risk and compare hashes before a review.

    These hashes are NOT issuer signatures. They only guard accidental
    mismatch in offline QA review; arbitrary callers can forge inputs.
    """
    issues: list[str] = []
    valid_challenge = isinstance(challenge, Stage48ApprovalChallenge) and (
        isinstance(challenge.account_id, str)
        and isinstance(challenge.order_id, str)
        and isinstance(challenge.snapshot_hash, str)
        and _HEX64.fullmatch(challenge.snapshot_hash) is not None
        and challenge.target_entity_id == (
            "STAGE48:PAPER:" + challenge.account_id + ":" + challenge.order_id
        )
        and challenge.order_state == "PENDING_APPROVAL"
        and challenge.simulated_only is True
        and challenge.external_identity_verified is False
        and challenge.independently_enforced_authority is False
        and challenge.live_orders_transmitted == 0
    )
    if not valid_challenge:
        issues.append("INVALID_STAGE48_CHALLENGE")

    valid_link = (
        valid_challenge
        and isinstance(intent, Stage56SyntheticIntent)
        and isinstance(account, Stage56SyntheticRiskState)
        and challenge.account_id == account.account_id
        and challenge.order_id == intent.request_id
    )
    if not valid_link:
        issues.append("PAPER_ORDER_ACCOUNT_RISK_IDENTITY_MISMATCH")

    if (not isinstance(expected_risk_policy_sha256, str)
        or _HEX64.fullmatch(expected_risk_policy_sha256) is None
        or not isinstance(expected_risk_input_sha256, str)
        or _HEX64.fullmatch(expected_risk_input_sha256) is None):
        issues.append("UNVERIFIED_EXPECTED_RISK_DIGESTS")

    decision = inspect_stage56_synthetic_risk(
        intent, quote, account, policy=policy, now=now,
    )
    if not decision.local_synthetic_screen_passed:
        issues.append("FRESH_LOCAL_RISK_RECHECK_VETO")
        issues.extend("STAGE56_" + name for name in decision.blockers)
    if (decision.policy_sha256 != expected_risk_policy_sha256
        or decision.input_sha256 is None
        or decision.input_sha256 != expected_risk_input_sha256):
        issues.append("RISK_POLICY_OR_INPUT_DIGEST_CHANGED")

    clean = not issues
    review_sha = None
    if clean:
        payload = json.dumps(
            ["STAGE57_UNTRUSTED_LOCAL_BINDING_ONLY_V1",
             challenge.account_id, challenge.order_id, challenge.snapshot_hash,
             decision.policy_sha256, decision.input_sha256],
            ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        )
        review_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return Stage57ApprovalRiskReview(
        schema_version=1,
        account_id=challenge.account_id if valid_challenge else "UNVERIFIED",
        paper_order_id=challenge.order_id if valid_challenge else "UNVERIFIED",
        local_consistency_observed=clean,
        blockers=tuple(dict.fromkeys(issues)),
        order_snapshot_sha256=challenge.snapshot_hash if valid_challenge else None,
        risk_policy_sha256=decision.policy_sha256,
        risk_input_sha256=decision.input_sha256,
        local_review_sha256=review_sha,
        local_risk_screen_passed=decision.local_synthetic_screen_passed,
    )
