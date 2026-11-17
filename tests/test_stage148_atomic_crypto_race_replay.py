"""Stage148: concurrency, replay and kill-race for opt-in Stage147 synthetic caps.

No broker route, no user identity proof, no global mandatory Risk & Veto claim.
Tests exercise the exact signed TEST-permit + SQLite atomic boundary.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3

import pytest

from nexus_titan.operations.crypto_spot_independent_review import CryptoSpotReviewPolicy
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBlocked, CryptoPaperBook, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

KEY = b"STAGE148_SYNTHETIC_ATOMIC_REPLAY_ONLY".ljust(32, b"Q")
LIMITS = CryptoPaperLimits(200_000, 100_000, 150_000, 10_000, paper_enabled=True)
POLICY = CryptoSpotReviewPolicy(49_000, 70_000, 9_000, 20, 100)


def make_book(tmp_path):
    path = tmp_path / "stage148-atomic.sqlite"
    book = CryptoPaperBook(path=path, account_id="stage148-review",
                           limits=LIMITS, atomic_review_policy=POLICY,
                           verification_key=KEY)
    return book, path


def make_intent(operation_id, epoch=100):
    # 0.008 BTC @ USDT 50,000 -> USDT 400 notional.
    return CryptoPaperIntent(operation_id, "BUY", 8_000, 5_000_000, epoch)


def signed(book, intent, *, now=101, head=None):
    state = book.snapshot() if head is None else head
    return seal_crypto_paper_permit(
        KEY, account_id=book.account_id, revision=state.journal_revision,
        tip=state.journal_tip, intent=intent, expires_epoch=now+5,
    )


def test_2_concurrent_valid_same_head_permits_do_not_double_admit(tmp_path):
    book, _ = make_book(tmp_path)
    head = book.snapshot()
    intents = [make_intent("simultaneous-a"), make_intent("simultaneous-b")]
    permits = [signed(book, i, head=head) for i in intents]

    def attempt(index):
        try:
            result, duplicate = book.apply(
                intents[index], permits[index],
                now_epoch=101, human_approved=True,
            )
            assert not duplicate
            return "COMMITTED"
        except CryptoPaperBlocked:
            return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcome = list(pool.map(attempt, (0, 1)))
    assert sorted(outcome) == ["COMMITTED", "DENIED"]
    s = book.snapshot()
    assert s.journal_revision == 1 and s.position_microcoin == 8_000
    assert s.cash_cents+s.remaining_cost_basis_cents == s.initial_cents+s.realized_net_pnl_cents
    assert s.live_trading_enabled is False


def test_fresh_valid_second_permit_cannot_exceed_independent_exposure(tmp_path):
    book, _ = make_book(tmp_path)
    a = make_intent("first-entry")
    first, replay = book.apply(a, signed(book, a), now_epoch=101, human_approved=True)
    assert not replay and first.journal_revision == 1
    b = make_intent("second-entry", 101)
    permit = signed(book, b, now=102)
    with pytest.raises(CryptoPaperBlocked, match="Atomic independent capital or risk veto"):
        book.apply(b, permit, now_epoch=102, human_approved=True)
    assert book.snapshot() == first


def test_old_signed_exact_operation_replays_but_cannot_insert_new_trade(tmp_path):
    book, _ = make_book(tmp_path)
    intent = make_intent("idempotent")
    permit = signed(book, intent)
    first, duplicate = book.apply(intent, permit, now_epoch=101, human_approved=True)
    assert not duplicate
    same, duplicate = book.apply(intent, permit, now_epoch=500, human_approved=True)
    assert duplicate and same == first
    new = make_intent("new-at-old-head", 101)
    wrong = signed(book, new, head=book._initial(), now=102)
    with pytest.raises(CryptoPaperBlocked):
        book.apply(new, wrong, now_epoch=102, human_approved=True)
    assert book.snapshot() == first


def test_kill_between_precheck_and_atomic_commit_does_not_create_buy(tmp_path, monkeypatch):
    book, _ = make_book(tmp_path)
    intent = make_intent("kill-interleaved")
    permit = signed(book, intent)
    original_atomic = book._apply

    def stop_before_atomic(*args, **kwargs):
        original_atomic("kill-just-before-commit", {
            "kind": "KILL", "operation_id": "kill-just-before-commit"
        })
        return original_atomic(*args, **kwargs)

    monkeypatch.setattr(book, "_apply", stop_before_atomic)
    with pytest.raises(CryptoPaperBlocked):
        book.apply(intent, permit, now_epoch=101, human_approved=True)
    state = book.snapshot()
    assert state.kill_active and state.journal_revision == 1
    assert state.position_microcoin == 0
    assert state.cash_cents == state.initial_cents
    assert not state.live_trading_enabled


def test_settings_hash_tamper_fails_closed_on_restart(tmp_path):
    book, path = make_book(tmp_path)
    before = book.snapshot()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE crypto_meta SET settings_sha=?", ("0" * 64,))
    with pytest.raises(CryptoPaperBlocked, match="metadata"):
        book.snapshot()
    with pytest.raises(CryptoPaperBlocked, match="mismatch"):
        make_book(tmp_path)
    assert before.journal_revision == 0
