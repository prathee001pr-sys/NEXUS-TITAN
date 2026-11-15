from datetime import datetime, timedelta, timezone

from nexus_titan.intelligence.evidence_integrity import EvidenceEnvelope, verify_evidence_envelope


def test_evidence_envelope_accepts_matching_fresh_payload():
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    envelope = EvidenceEnvelope.build(evidence_id="e-1", source_id="feed-a",
                                      payload={"symbol": "NIFTY", "close": 25000},
                                      observed_at=now.isoformat())
    assert verify_evidence_envelope(envelope, now=now) == (True, ())


def test_evidence_envelope_detects_payload_tampering():
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    envelope = EvidenceEnvelope.build(evidence_id="e-2", source_id="feed-a",
                                      payload={"close": 25000}, observed_at=now.isoformat())
    tampered = EvidenceEnvelope(envelope.evidence_id, envelope.source_id,
                                {"close": 25001}, envelope.sha256, envelope.observed_at)
    ok, issues = verify_evidence_envelope(tampered, now=now)
    assert not ok
    assert "evidence_digest_mismatch" in issues


def test_evidence_envelope_rejects_stale_payload():
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    envelope = EvidenceEnvelope.build(evidence_id="e-3", source_id="feed-a",
                                      payload={"close": 25000},
                                      observed_at=(now - timedelta(minutes=10)).isoformat())
    ok, issues = verify_evidence_envelope(envelope, now=now, max_age_seconds=60)
    assert not ok
    assert "evidence_stale" in issues


def test_evidence_envelope_rejects_naive_timestamp():
    envelope = EvidenceEnvelope.build(evidence_id="e-4", source_id="feed-a",
                                      payload={"close": 25000}, observed_at="2026-11-01T12:00:00")
    ok, issues = verify_evidence_envelope(envelope)
    assert not ok
    assert "evidence_timestamp_invalid" in issues


def test_evidence_envelope_rejects_future_timestamp():
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    envelope = EvidenceEnvelope.build(evidence_id="e-5", source_id="feed-a",
                                      payload={"close": 25000},
                                      observed_at=(now + timedelta(minutes=2)).isoformat())
    ok, issues = verify_evidence_envelope(envelope, now=now)
    assert not ok
    assert "evidence_timestamp_in_future" in issues


def test_master_orchestrator_rejects_tampered_verified_evidence():
    from nexus_titan.core.master_integration import MasterTradingOrchestrator
    now = datetime.now(timezone.utc)
    envelope = EvidenceEnvelope.build(
        evidence_id="e-master", source_id="source-1",
        payload={"role": "MOMENTUM", "action": "BUY", "reason": "positive momentum",
                 "invalidation": "momentum reversal"},
        observed_at=now.isoformat(),
    )
    tampered = EvidenceEnvelope(envelope.evidence_id, envelope.source_id,
                                {**envelope.payload, "reason": "tampered"},
                                envelope.sha256, envelope.observed_at)
    import pytest
    with pytest.raises(ValueError, match="evidence_digest_mismatch"):
        MasterTradingOrchestrator().run_cycle_from_verified_evidence(
            state=None, evidence_envelopes=[tampered], risk_request=None,
            execution_request=None, expected_edge_bps=0,
        )
