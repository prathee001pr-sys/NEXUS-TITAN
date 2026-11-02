import json
import pytest
from nexus_titan.shadow.validation import (
    ShadowEvent, ShadowEvidenceLedger, reconcile_session, evaluate_shadow_readiness,
)


def test_append_only_ledger_hash_chain_and_read(tmp_path):
    path = tmp_path / "shadow.jsonl"
    ledger = ShadowEvidenceLedger(path)
    event = ShadowEvent("2026-11-02", "2026-11-02T09:15:00+05:30", "SESSION_OPEN", "S1", {"capital": 50000})
    first = ledger.append(event)
    assert len(first) == 64
    assert ledger.events("2026-11-02") == (event,)
    reopened = ShadowEvidenceLedger(path)
    assert reopened.append(ShadowEvent("2026-11-02", "2026-11-02T15:30:00+05:30", "SESSION_CLOSE", "S1-CLOSE", {}))


def test_ledger_rejects_non_monotonic_time(tmp_path):
    ledger = ShadowEvidenceLedger(tmp_path / "events.jsonl")
    ledger.append(ShadowEvent("2026-11-02", "2026-11-02T10:00:00+05:30", "A", "1", {}))
    with pytest.raises(ValueError, match="monotonic"):
        ledger.append(ShadowEvent("2026-11-02", "2026-11-02T09:00:00+05:30", "B", "2", {}))


def test_ledger_detects_tampering(tmp_path):
    path = tmp_path / "events.jsonl"
    ShadowEvidenceLedger(path).append(ShadowEvent("2026-11-02", "2026-11-02T10:00:00+05:30", "A", "1", {"x": 1}))
    row = json.loads(path.read_text())
    row["event"]["payload"]["x"] = 2
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="hash verification"):
        ShadowEvidenceLedger(path)


def test_session_reconciliation_success_and_failure():
    good = reconcile_session(session_date="2026-11-02", opening_balance=50000, closing_balance=50100,
        realized_pnl=120, fees=20, expected_event_count=4, observed_event_count=4)
    assert good.is_reconciled and good.status == "RECONCILED"
    bad = reconcile_session(session_date="2026-11-02", opening_balance=50000, closing_balance=50100,
        realized_pnl=120, fees=20, expected_event_count=4, observed_event_count=3)
    assert not bad.is_reconciled and bad.status == "REVIEW_REQUIRED"


def test_readiness_requires_all_evidence_and_never_promotes():
    weak = evaluate_shadow_readiness(session_count=3, reconciled_sessions=3, closed_trades=5,
        data_provenance_verified=False, execution_calibration_verified=False)
    assert not weak["eligible_for_human_review"]
    assert weak["strategy_promotion"] == "NOT_AUTOMATIC"
    assert weak["live_trading"] == "DISABLED"
    strong = evaluate_shadow_readiness(session_count=20, reconciled_sessions=20, closed_trades=30,
        data_provenance_verified=True, execution_calibration_verified=True)
    assert strong["eligible_for_human_review"]


def test_readiness_rejects_invalid_counts():
    with pytest.raises(ValueError):
        evaluate_shadow_readiness(session_count=-1, reconciled_sessions=0, closed_trades=0,
            data_provenance_verified=False, execution_calibration_verified=False)
