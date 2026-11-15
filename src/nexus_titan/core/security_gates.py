"""Durable cryptographic approvals and evidence-driven G0-G9 release gates."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class SignedApprovalToken:
    """Cryptographically bound human approval token with expiry and one-time nonce."""

    token_id: str
    actor: str
    role: str
    target_entity_id: str
    snapshot_hash: str
    issued_at_epoch: int
    expires_at_epoch: int
    signature_hex: str


class CryptographicApprovalVerifier:
    """HMAC-SHA256 verifier with SQLite-backed, cross-process replay protection.

    Keep the signing key in a secret manager/environment variable, never in this DB.
    The replay database should live on durable storage with restrictive OS permissions.
    """

    def __init__(
        self,
        secret_key: str,
        allowed_roles: tuple[str, ...] = ("RISK_OWNER", "PROJECT_OWNER", "HUMAN_APPROVER"),
        db_path: str | Path = "data/approval_replay.sqlite3",
    ) -> None:
        if not isinstance(secret_key, str) or len(secret_key.strip()) < 16:
            raise ValueError("secret_key must be at least 16 characters.")
        roles = tuple(str(role).strip() for role in allowed_roles)
        if not roles or any(not role for role in roles):
            raise ValueError("allowed_roles must contain non-empty role names.")
        self._secret = secret_key.encode("utf-8")
        self.allowed_roles = set(roles)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS consumed_approval_tokens (
                token_id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                role TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                consumed_at_epoch INTEGER NOT NULL
            )""")
            # Stage57: negative-only persistent revocation. This never grants
            # approval or authenticates a human actor. Share this SAME SQLite
            # transaction domain with consumed nonces to prevent revocation /
            # consumption races between cooperating verifier instances.
            db.execute("""CREATE TABLE IF NOT EXISTS revoked_approval_tokens (
                token_id TEXT PRIMARY KEY,
                revoked_at_epoch INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS revoked_approval_actors (
                actor TEXT PRIMARY KEY,
                revoked_at_epoch INTEGER NOT NULL
            )""")
        # Approval replay metadata should not be readable by other local users.
        # The parent directory must also be protected by the deployment operator.
        if os.name == "posix" and self.db_path.exists():
            os.chmod(self.db_path, 0o600)

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _compute_mac(
        self, token_id: str, actor: str, role: str, target_entity_id: str,
        snapshot_hash: str, issued_at: int, expires_at: int,
    ) -> str:
        # Canonical JSON avoids delimiter ambiguity in attacker-controlled fields.
        payload = json.dumps(
            [token_id, actor, role, target_entity_id, snapshot_hash, issued_at, expires_at],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def issue_token(
        self, *, token_id: str, actor: str, role: str, target_entity_id: str,
        snapshot_hash: str, ttl_seconds: int = 900, now_epoch: int | None = None,
    ) -> SignedApprovalToken:
        fields = (token_id, actor, target_entity_id, snapshot_hash)
        if any(not isinstance(item, str) or not item.strip() for item in fields):
            raise ValueError("token_id, actor, target_entity_id, and snapshot_hash are required.")
        if not isinstance(role, str) or role not in self.allowed_roles:
            raise PermissionError(f"Role '{role}' is not authorized to sign approvals.")
        if any(len(item) > 512 for item in fields):
            raise ValueError("Approval token string fields exceed the 512-character limit.")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 10 <= ttl_seconds <= 86_400:
            raise ValueError("ttl_seconds must be an integer between 10 seconds and 24 hours.")
        if now_epoch is not None and (isinstance(now_epoch, bool) or not isinstance(now_epoch, int)):
            raise ValueError("now_epoch must be an integer epoch timestamp.")
        issued = int(time.time()) if now_epoch is None else now_epoch
        expires = issued + ttl_seconds
        mac = self._compute_mac(token_id, actor, role, target_entity_id, snapshot_hash, issued, expires)
        return SignedApprovalToken(token_id, actor, role, target_entity_id, snapshot_hash, issued, expires, mac)

    @staticmethod
    def _revocation_subject(value: str, kind: str) -> str:
        # Same max-length bound as existing signed tokens. A revoked identity
        # cannot be reinstated using a different in-process verifier instance.
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise PermissionError(kind + " must be a nonempty bounded string")
        return value

    def revoke_token(self, token_id: str, *, now_epoch: int | None = None) -> bool:
        """Permanently deny a token ID in the replay DB. Idempotent, deny-only.

        This is NOT authenticated administration; a real deployment needs an
        independent operator/control-plane boundary before exposing it.
        """
        subject = self._revocation_subject(token_id, "Token ID")
        if now_epoch is not None and (type(now_epoch) is not int or now_epoch < 0):
            raise PermissionError("Invalid revocation timestamp")
        current = int(time.time()) if now_epoch is None else now_epoch
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO revoked_approval_tokens VALUES (?,?)",
                (subject, current),
            )
            db.commit()
        finally:
            db.close()
        return True

    def revoke_actor(self, actor: str, *, now_epoch: int | None = None) -> bool:
        """Permanently deny every current/future signed token for this label.

        A self-claimed 'actor' is only an HMAC field, NOT verified human ID.
        Does NOT recall already accepted paper orders or fill history.
        """
        subject = self._revocation_subject(actor, "Actor label")
        if now_epoch is not None and (type(now_epoch) is not int or now_epoch < 0):
            raise PermissionError("Invalid revocation timestamp")
        current = int(time.time()) if now_epoch is None else now_epoch
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO revoked_approval_actors VALUES (?,?)",
                (subject, current),
            )
            db.commit()
        finally:
            db.close()
        return True

    def local_revocation_status(self, *, token_id: str, actor: str) -> dict[str, bool]:
        """Read-only local labels; not signer identity or token validity."""
        token_key = self._revocation_subject(token_id, "Token ID")
        actor_key = self._revocation_subject(actor, "Actor label")
        db = self._connect()
        try:
            token_revoked = db.execute(
                "SELECT 1 FROM revoked_approval_tokens WHERE token_id=?",
                (token_key,),
            ).fetchone() is not None
            actor_revoked = db.execute(
                "SELECT 1 FROM revoked_approval_actors WHERE actor=?",
                (actor_key,),
            ).fetchone() is not None
        finally:
            db.close()
        return {
            "token_revoked": token_revoked,
            "actor_revoked": actor_revoked,
        }

    def verify_and_consume(
        self, token: SignedApprovalToken, *, expected_target_id: str,
        expected_snapshot_hash: str, now_epoch: int | None = None,
    ) -> bool:
        """Verify token fields/signature and atomically consume token_id exactly once."""
        if now_epoch is not None and (isinstance(now_epoch, bool) or not isinstance(now_epoch, int)):
            raise PermissionError("now_epoch must be an integer epoch timestamp.")
        current = int(time.time()) if now_epoch is None else now_epoch
        if not isinstance(token, SignedApprovalToken):
            raise PermissionError("Approval token has an invalid type.")
        if any(not isinstance(value, str) or not value.strip() for value in (
            token.token_id, token.actor, token.role, token.target_entity_id,
            token.snapshot_hash, token.signature_hex,
        )):
            raise PermissionError("Approval token contains missing or invalid fields.")
        if token.role not in self.allowed_roles:
            raise PermissionError(f"Unauthorized signer role: {token.role}")
        if (isinstance(token.issued_at_epoch, bool) or not isinstance(token.issued_at_epoch, int)
                or isinstance(token.expires_at_epoch, bool) or not isinstance(token.expires_at_epoch, int)):
            raise PermissionError("Approval token validity timestamps must be integers.")
        if token.issued_at_epoch > current:
            raise PermissionError("Approval token is not yet valid.")
        token_ttl = token.expires_at_epoch - token.issued_at_epoch
        if token_ttl < 10 or token_ttl > 86_400 or current > token.expires_at_epoch:
            raise PermissionError("Approval token has expired or has an invalid validity window.")
        if token.target_entity_id != expected_target_id or token.snapshot_hash != expected_snapshot_hash:
            raise PermissionError("Approval token target or snapshot_hash mismatch.")
        expected_mac = self._compute_mac(
            token.token_id, token.actor, token.role, token.target_entity_id,
            token.snapshot_hash, token.issued_at_epoch, token.expires_at_epoch,
        )
        if not hmac.compare_digest(token.signature_hex, expected_mac):
            raise PermissionError("Invalid cryptographic signature on approval token.")

        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM revoked_approval_tokens WHERE token_id=?",
                (token.token_id,),
            ).fetchone() is not None:
                raise PermissionError("Approval token ID was revoked")
            if db.execute(
                "SELECT 1 FROM revoked_approval_actors WHERE actor=?",
                (token.actor,),
            ).fetchone() is not None:
                raise PermissionError("Approval actor label was revoked")
            try:
                db.execute(
                    "INSERT INTO consumed_approval_tokens VALUES (?,?,?,?,?,?)",
                    (token.token_id, token.actor, token.role, token.target_entity_id,
                     token.snapshot_hash, current),
                )
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise PermissionError("Approval replay detected: token_id has already been consumed.") from exc
            db.commit()
        finally:
            db.close()
        return True


@dataclass(frozen=True)
class QualityGateCheck:
    """Status of one evidence-backed release gate."""

    gate_id: str
    name: str
    status: Literal["PASSED_CODE_VERIFIED", "EXTERNAL_INPUT_REQUIRED", "FAILED"]
    evidence: str
    fail_action: str


def evaluate_g0_to_g9_quality_gates(
    *,
    tests_passed: int,
    golden_accounting_reconciled: bool,
    shadow_50k_reconciled: bool,
    tests_total: int = 0,
    test_run_success: bool = False,
    test_run_attempted: bool = False,
    source_api_parity_verified: bool = False,
    has_licensed_15yr_dataset: bool = False,
    futures_options_golden_fixtures_passed: bool = False,
    approval_replay_protection_verified: bool = False,
    stale_feed_protection_verified: bool = False,
    kill_switch_verified: bool = False,
    daily_loss_lockout_verified: bool = False,
    microstructure_golden_fixtures_passed: bool = False,
    has_external_pentest_signoff: bool = False,
    ops_recovery_verified: bool = False,
    multi_day_shadow_observation_verified: bool = False,
    owner_release_signed: bool = False,
    live_trading_disabled: bool = True,
) -> dict[str, Any]:
    """Evaluate gates from explicit evidence; never infer a pass from a hard-coded count."""
    if not live_trading_disabled:
        raise PermissionError("CRITICAL: G9 Zero-Live Release Gate violated — live trading must remain disabled.")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (tests_passed, tests_total)):
        raise ValueError("tests_passed and tests_total must be non-negative integers.")

    full_test_pass = test_run_success and tests_total > 0 and tests_passed == tests_total
    g0_status = "PASSED_CODE_VERIFIED" if full_test_pass else ("FAILED" if test_run_attempted else "EXTERNAL_INPUT_REQUIRED")
    approval_safety = all((approval_replay_protection_verified, stale_feed_protection_verified,
                           kill_switch_verified, daily_loss_lockout_verified))
    pre_release_evidence = all((full_test_pass, source_api_parity_verified,
                                has_licensed_15yr_dataset, golden_accounting_reconciled,
                                futures_options_golden_fixtures_passed, shadow_50k_reconciled,
                                microstructure_golden_fixtures_passed, approval_safety,
                                has_external_pentest_signoff, ops_recovery_verified,
                                multi_day_shadow_observation_verified))

    checks = [
        ("G0", "Build reproducibility", g0_status,
         f"Test runner success={test_run_success}; passed={tests_passed}; total={tests_total}.", "Fix CI/build failures; no promotion."),
        ("G1", "API/behavior correctness", "PASSED_CODE_VERIFIED" if source_api_parity_verified else "EXTERNAL_INPUT_REQUIRED",
         "Independent source/API parity evidence explicitly supplied." if source_api_parity_verified else "Path mapping and tests alone do not establish complete API/behavior parity.", "Keep adapted API parity audit open."),
        ("G2", "Data integrity", "PASSED_CODE_VERIFIED" if has_licensed_15yr_dataset else "EXTERNAL_INPUT_REQUIRED",
         "Licensed 15-year, 1-minute dataset evidence supplied." if has_licensed_15yr_dataset else "Vendor licence, provenance, timezone, gaps and point-in-time metadata are not verified.", "Block strategy promotion on synthetic/unverified data."),
        ("G3", "Accounting accuracy", "PASSED_CODE_VERIFIED" if (golden_accounting_reconciled and futures_options_golden_fixtures_passed) else "FAILED",
         f"Independent cash/fees/partial fills reconciled={golden_accounting_reconciled}; futures/options golden fixtures={futures_options_golden_fixtures_passed}.", "Disable affected instrument type until golden fixtures reconcile."),
        ("G4", "Risk and approval safety", "PASSED_CODE_VERIFIED" if approval_safety else "FAILED",
         f"Durable replay={approval_replay_protection_verified}; stale feed={stale_feed_protection_verified}; kill switch={kill_switch_verified}; daily loss={daily_loss_lockout_verified}.", "Fail closed; no fresh entries or promotion."),
        ("G5", "Execution realism", "PASSED_CODE_VERIFIED" if (shadow_50k_reconciled and microstructure_golden_fixtures_passed) else "FAILED",
         f"₹50k paper ledger reconciled={shadow_50k_reconciled}; execution golden fixtures={microstructure_golden_fixtures_passed}.", "Label execution as simplified; do not make performance claims."),
        ("G6", "Independent security", "PASSED_CODE_VERIFIED" if has_external_pentest_signoff else "EXTERNAL_INPUT_REQUIRED",
         "Independent security assessment sign-off supplied." if has_external_pentest_signoff else "No independent pentest sign-off supplied.", "No production rollout."),
        ("G7", "Operations and recovery", "PASSED_CODE_VERIFIED" if ops_recovery_verified else "EXTERNAL_INPUT_REQUIRED",
         "Crash/restart, backup and restore evidence supplied." if ops_recovery_verified else "Operational recovery acceptance evidence is missing.", "No unattended operation."),
        ("G8", "Paper evidence", "PASSED_CODE_VERIFIED" if (shadow_50k_reconciled and multi_day_shadow_observation_verified and has_licensed_15yr_dataset) else "EXTERNAL_INPUT_REQUIRED",
         f"Shadow reconciliation={shadow_50k_reconciled}; multi-day observation={multi_day_shadow_observation_verified}; licensed data={has_licensed_15yr_dataset}.", "Continue controlled shadow observation; do not promote strategy."),
        ("G9", "Release sign-off", "PASSED_CODE_VERIFIED" if (owner_release_signed and pre_release_evidence) else "EXTERNAL_INPUT_REQUIRED",
         f"Owner signed={owner_release_signed}; all preceding evidence complete={pre_release_evidence}; live trading disabled.", "Keep release blocked and PR draft."),
    ]
    gates = [QualityGateCheck(*row) for row in checks]
    return {
        "total_gates": len(gates),
        "code_verified_gates": sum(g.status == "PASSED_CODE_VERIFIED" for g in gates),
        "external_input_required_gates": sum(g.status == "EXTERNAL_INPUT_REQUIRED" for g in gates),
        "failed_gates": sum(g.status == "FAILED" for g in gates),
        "live_trading_disabled": live_trading_disabled,
        "gates": [asdict(g) for g in gates],
    }
