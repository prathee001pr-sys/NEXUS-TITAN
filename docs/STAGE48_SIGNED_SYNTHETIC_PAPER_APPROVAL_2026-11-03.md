# NEXUS TITAN — Stage 48: Signed Synthetic Manual Approval (Additive)

**Date:** 2026-11-03  
**Source branch:** `feature/stage48-signed-paper-approval-2026-11-03`  
**Parent:** Stage47 draft PR #39  
**Status:** LOCAL SIGNED APPROVAL PROTOTYPE; NOT EXTERNAL IDENTITY / LIVE AUTHORIZATION

## What this stage implements

Existing Stage43 and Stage47 support guarded paper intents and manual approval
but Stage43 accepts any configured Python callback returning `True`. Such a
callback alone is **not** a verified signer, identity provider or trusted risk
boundary. Stage48 creates a separate opt-in manual approval path that
**defaults to denial** unless a caller supplies a valid, signed, unexpired,
one-time token for the exact currently pending synthetic BUY.

- `src/nexus_titan/operations/signed_paper_approval.py`
  - `open_stage48_signed_paper_session(config, verifier=...)` boots Stage43
    with a special default-deny callback installed from startup.
  - `request_synthetic_buy(...)` goes through Stage47 Risk & Veto, Stage45
    conservative flatness and Stage43's manual paper gateway; adds the new
    order ID to *in-process* known provenance.
  - `pending_challenge(order_id)` constructs a canonical SHA256 snapshot of
    account ID, durable virtual account revision, effective risk-policy hash,
    exact order ID, order field fingerprint, state, quantity and fills. It
    returns a target ID and signing hash **without** issuing approval.
  - `approve_pending_buy(order_id=..., token=...)` verifies exact target and
    hash, paper-approver role and unmodified order policy; briefly authorizes
    **one same-thread callback invocation** and uses existing
    `CryptographicApprovalVerifier.verify_and_consume()` to check HMAC
    signature, token lifetime and persistent one-time nonce. A valid token
    changes PENDING_APPROVAL -> ACCEPTED; this **does not fill a paper order**.
    Without this session method, the callback rejects direct `approve_order`.
  - The adapter refuses a second approval window, replayed token ID,
    expired or future-dated signature, cross-account/wrong-order tokens,
    unexpected role, stale process/revision, killed account, risk-policy or
    order-field drift. On restart the provenance set is empty; previously
    pending orders **fail closed** pending separate manual recovery design.
  - The HMAC token signer's key is *supplied from outside this component*;
    Stage48 does not generate production credentials or mint approvals.
    The verifier replay database must be distinct from both paper books and
    must be protected by appropriate filesystem permissions.

- `scripts/run_stage48_signed_paper_smoke.py` uses isolated temporary
  SQLite and an ephemeral **demo-only** local secret. Tests an accepted
  but unfilled synthetic order, unsigned callback refusal and nonce replay
  denial; prints **no secret/key/token**. No external data or network.

- `tests/test_stage48_signed_paper_approval.py` tests legitimate local
  signature acceptance plus hostile/failure scenarios: expired/future token,
  signature/actor/role/order tampering, loss of signed snapshot/risk
  fingerprint, kill switch, unknown source, wrong account, old pending
  restart, replay across later orders, direct callback denial and CLI smoke.

## Explicit safety limitations

1. **HMAC possession is not verified human identity.** The synthetic signer
   in tests can create arbitrary tokens. In production, key issuance and
   human approval require *independent identity provider, isolated signing
   service/HSM or secret manager, authorization policy, audit and revocation*.
   The current implementation makes **no claim of those controls**.
2. This is an **optional in-process Python facade**, not an independent,
   unbypassable service. Existing legacy APIs and direct mutable account
   objects remain accessible; callers with code access can replace the
   callback or alter modules. Do not market it as global Risk & Veto.
3. The verifier commits a spent token in SQLite *before* the virtual
   account persists ACCEPTED. If latter persistence fails the token remains
   consumed; this is conservative, but **not a cross-database atomic commit**.
   A manual recovery procedure is still needed.
4. Quote/market risk may change after order creation and signature. Stage47
   quote integrity is synthetic, and Stage43 does not validate a real
   authenticated feed at approval or fill time.
5. This Stage48 path only signs **new synthetic EQUITY_DELIVERY BUY**
   intentions. It does not claim to sign options/futures, automate SELL or
   emergency exits, or enable automatic real or paper fills. Risk-reducing
   emergency paths in the underlying account are preserved.
6. No licensed NSE market data, external source identity, multi-day real
   shadow acceptance, robust operator identity, owner release, completed
   dashboard integration, or live broker connectivity has been verified.
7. GitHub branch stack remains draft and unmerged. CI success proves
   software behavior on offline fixtures, not production readiness.

## Verification

```bash
python scripts/run_stage48_signed_paper_smoke.py
python -m pytest -q tests/test_stage48_signed_paper_approval.py
python -m pytest -q
```

Mark Stage48 local coding milestone verified only after the final PR-head
3/3 GitHub Actions Python 3.11/3.12/3.13 matrix is green, and record actual
test counts and run ID in PR description. Do not merge without user/owner
review. Stage49 should evaluate a true single-capital-authority or verified
isolation of virtual and research cash ledgers *before* any wider admission.
