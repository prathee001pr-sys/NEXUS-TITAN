from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_preflight", ROOT / "scripts" / "release_preflight.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_source_fingerprint_is_sha256_hex():
    value = MODULE.source_fingerprint()
    assert len(value) == 64
    assert all(ch in "0123456789abcdef" for ch in value)


def test_secret_scanner_returns_structured_findings():
    findings = MODULE.scan_secrets()
    assert isinstance(findings, list)
    assert all({"rule", "path", "line"}.issubset(item) for item in findings)


def test_release_preflight_never_claims_production_approval():
    text = (ROOT / "scripts" / "release_preflight.py").read_text(encoding="utf-8")
    assert '"live_trading_enabled": False' in text
    assert '"NOT_VERIFIED"' in text
