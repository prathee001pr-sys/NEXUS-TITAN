import pytest

from nexus_titan.core.audit import AuditLedger


def test_audit_records_are_hash_chained_and_verify():
    ledger = AuditLedger()
    first = ledger.append(actor="system", action="boot", outcome="success")
    second = ledger.append(actor="user", action="paper_mode", outcome="enabled")
    assert second.previous_hash == first.record_hash
    assert ledger.verify()


def test_records_returns_immutable_collection():
    ledger = AuditLedger()
    ledger.append(actor="system", action="boot", outcome="success")
    assert isinstance(ledger.records(), tuple)


def test_required_fields_are_validated():
    with pytest.raises(ValueError):
        AuditLedger().append(actor=" ", action="boot", outcome="success")


def test_non_json_details_are_rejected():
    with pytest.raises(TypeError):
        AuditLedger().append(actor="system", action="boot", outcome="ok",
                             details={"unsupported": object()})
