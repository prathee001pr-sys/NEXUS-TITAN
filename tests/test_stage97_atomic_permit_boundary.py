"""Real synthetic Stage97 atomic admission regression for unguarded _apply bypass.

This covers a brokerless local HMAC TEST key only; never human identity or live orders.
"""
from dataclasses import asdict, replace

import pytest

from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBlocked, CryptoPaperBook, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

KEY = b"ATOMIC_BOUNDARY_LOCAL_TEST_ONLY".ljust(32, b"Q")


def _case(tmp_path):
    book = CryptoPaperBook(
        path=tmp_path / "crypto-atomic.sqlite", account_id="synthetic-atomic",
        limits=CryptoPaperLimits(200_000, 100_000, 150_000, 10_000, paper_enabled=True),
        verification_key=KEY,
    )
    intent = CryptoPaperIntent("atomic-entry", "BUY", 10_000, 5_000_000, 100)
    notional = 50_000
    payload = {
        "kind": "TRADE", "operation_id": intent.operation_id,
        "intent": asdict(intent), "notional_cents": notional,
        "fee_cents": 50,
    }
    state = book.snapshot()
    permit = seal_crypto_paper_permit(
        KEY, account_id=book.account_id, revision=state.journal_revision,
        tip=state.journal_tip, intent=intent, expires_epoch=110,
    )
    return book, intent, payload, permit


@pytest.mark.parametrize("attack", [
    "no_permit", "forged_permit", "no_time", "no_approval", "stale_time",
    "stale_revision", "different_intent", "altered_fee", "altered_notional",
    "unsigned_type", "extra_payload", "false_paper_context", "wrong_key",
])
def test_atomic_private_entrypoint_rejects_untrusted_trade(tmp_path, attack):
    book, intent, payload, permit = _case(tmp_path)
    kwargs = {"permit": permit, "now_epoch": 101, "human_approved": True}
    if attack == "no_permit": kwargs["permit"] = None
    elif attack == "forged_permit": kwargs["permit"] = replace(permit, signature_hex="0" * 64)
    elif attack == "no_time": kwargs["now_epoch"] = None
    elif attack == "no_approval": kwargs["human_approved"] = False
    elif attack == "stale_time": kwargs["now_epoch"] = 150
    elif attack == "stale_revision": kwargs["permit"] = replace(permit, expected_revision=1)
    elif attack == "different_intent": payload["intent"]["quantity_microcoin"] = 20_000
    elif attack == "altered_fee": payload["fee_cents"] = 0
    elif attack == "altered_notional": payload["notional_cents"] = 40_000
    elif attack == "unsigned_type": kwargs["permit"] = object()
    elif attack == "extra_payload": payload["self_authorized"] = True
    elif attack == "false_paper_context": kwargs["autonomous"] = True
    elif attack == "wrong_key":
        kwargs["permit"] = seal_crypto_paper_permit(
            b"X" * 32, account_id=book.account_id, revision=0,
            tip=book.snapshot().journal_tip, intent=intent, expires_epoch=110,
        )
    with pytest.raises(CryptoPaperBlocked):
        book._apply(intent.operation_id, payload, **kwargs)
    state = book.snapshot()
    assert state.journal_revision == 0
    assert state.position_microcoin == 0
    assert state.cash_cents == state.initial_cents
    assert not state.live_trading_enabled and not state.exchange_orders_transmitted


def test_atomic_private_entrypoint_requires_signed_permit_even_for_disabled_book(tmp_path):
    book, intent, payload, permit = _case(tmp_path)
    book.limits = CryptoPaperLimits(200_000, 100_000, 150_000, 10_000, paper_enabled=False)
    with pytest.raises(CryptoPaperBlocked):
        book._apply(intent.operation_id, payload, permit=permit,
                    now_epoch=101, human_approved=True)


def test_public_paper_path_preserves_valid_permit_and_idempotent_replay(tmp_path):
    book, intent, _payload, permit = _case(tmp_path)
    state, duplicate = book.apply(intent, permit, now_epoch=101, human_approved=True)
    assert not duplicate and state.position_microcoin == 10_000
    state2, duplicate = book.apply(intent, permit, now_epoch=500, human_approved=True)
    assert duplicate and state2 == state


def test_atomic_private_entrypoint_valid_signed_same_policy_is_only_local_synthetic(tmp_path):
    book, intent, payload, permit = _case(tmp_path)
    state, duplicate = book._apply(intent.operation_id, payload, permit=permit,
                                    now_epoch=101, human_approved=True)
    assert not duplicate and state.journal_revision == 1
    assert state.position_microcoin == 10_000
    assert state.live_trading_enabled is False
    assert state.exchange_orders_transmitted == 0


def test_stop_kill_uses_separate_no_permit_emergency_path(tmp_path):
    book, _intent, _payload, _permit = _case(tmp_path)
    state, duplicate = book.stop("emergency-stop")
    assert not duplicate and state.kill_active and state.journal_revision == 1
    with pytest.raises(CryptoPaperBlocked):
        book._apply("fake-stop", {"kind": "KILL", "operation_id": "fake-stop", "extra": 1})
    assert book.snapshot().journal_revision == 1


def test_replay_after_write_does_not_accept_mutated_signed_payload(tmp_path):
    book, intent, payload, permit = _case(tmp_path)
    book.apply(intent, permit, now_epoch=101, human_approved=True)
    payload["fee_cents"] += 1
    with pytest.raises(CryptoPaperBlocked):
        book._apply(intent.operation_id, payload, permit=permit,
                    now_epoch=150, human_approved=True)
    assert book.snapshot().journal_revision == 1
