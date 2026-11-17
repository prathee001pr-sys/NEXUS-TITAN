"""Stage147 exact-source re-review remains a NO-GO static audit."""
from pathlib import Path
import shutil

from nexus_titan.diagnostics.stage97_execution_surface import (
    STAGE97_BASELINE_GIT_BLOB,
    STAGE97_PRE147_GIT_BLOB,
    REVIEWED_GATEWAY_BASELINE_GIT_BLOB,
    audit_stage97_paper_execution,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_STAGE147 = "ce6d362d1f6f1b18ec17402cded64db8b08444b6"
PREVIOUS_STAGE97 = "af3b87dbbfc718bc3ac2d46da1eb546c4b440de0"
GATEWAY = "43fc5a77e0ca908ba409116634519fbe4046acb3"


def test_stage147_source_repin_keeps_legacy_pin_and_no_go():
    assert STAGE97_BASELINE_GIT_BLOB == REVIEWED_STAGE147
    assert STAGE97_PRE147_GIT_BLOB == PREVIOUS_STAGE97
    assert REVIEWED_GATEWAY_BASELINE_GIT_BLOB == GATEWAY
    report = audit_stage97_paper_execution(ROOT)
    assert report["source_parse_ok"] is True
    assert report["pinned_source_match"] is True
    assert report["stage97_sha"] == REVIEWED_STAGE147
    assert report["gateway_sha"] == GATEWAY
    assert report["unknown_crypto_apply_calls"] == []
    assert report["unreviewed_atomic_apply_calls"] == []
    assert report["verdict"] == "BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY"
    assert report["mandatory_all_path_independent_risk_verified"] is False
    assert report["authenticated_human_authority_verified"] is False
    assert report["production_ready"] is False
    assert report["live_trading_authorized"] is False


def test_stage147_source_content_change_still_fails_closed(tmp_path):
    for name in ("stage97_crypto_paper.py", "crypto_spot_reviewed_paper.py"):
        original = ROOT / "src/nexus_titan/operations" / name
        dest = tmp_path / "src/nexus_titan/operations" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, dest)
    source = tmp_path / "src/nexus_titan/operations/stage97_crypto_paper.py"
    source.write_bytes(source.read_bytes() + b"\n# unexpected source drift\n")
    report = audit_stage97_paper_execution(tmp_path)
    assert report["source_parse_ok"] is True
    assert report["pinned_source_match"] is False
    assert report["verdict"] == "BLOCKED_SOURCE_DRIFT"
    assert report["production_ready"] is False
