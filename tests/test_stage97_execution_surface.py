"""Static all-path audit must not silently certify production risk control."""
from __future__ import annotations

from pathlib import Path
import json
import shutil

from nexus_titan.diagnostics.stage97_execution_surface import audit_stage97_paper_execution

ROOT=Path(__file__).resolve().parents[1]


def _synthetic_repo(tmp_path):
    for filename in ("stage97_crypto_paper.py","crypto_spot_reviewed_paper.py"):
        src=ROOT/"src/nexus_titan/operations"/filename
        dest=tmp_path/"src/nexus_titan/operations"/filename
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest)
    return tmp_path


def test_exact_source_structure_still_blocks_full_risk_signoff():
    result=audit_stage97_paper_execution(ROOT)
    assert result["source_parse_ok"] is True
    assert result["pinned_source_match"] is True
    assert result["public_stage97_apply"] is True
    assert result["opt_in_review_before_apply"] is True
    assert result["unknown_crypto_apply_calls"]==[]
    assert result["verdict"]=="BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY"
    assert result["mandatory_all_path_independent_risk_verified"] is False
    assert result["live_trading_authorized"] is False
    assert result["production_ready"] is False
    assert len(result["explicit_crypto_apply_calls"])==1


def test_json_receipt_is_serializable_and_has_no_secrets():
    report=json.dumps(audit_stage97_paper_execution(ROOT),sort_keys=True)
    assert "BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY" in report
    assert 'LOCAL_STUDY_DO_NOT_DEPLOY' not in report
    assert 'verification_key' not in report


def test_explicit_new_direct_book_apply_call_gets_flagged(tmp_path):
    root=_synthetic_repo(tmp_path)
    p=root/"src/nexus_titan/operations/crypto_backdoor.py"
    p.write_text('from .stage97_crypto_paper import CryptoPaperBook\n'
                 'def direct(book: CryptoPaperBook, intent, permit):\n'
                 '    return book.apply(intent, permit, now_epoch=10)\n')
    result=audit_stage97_paper_execution(root)
    assert result["verdict"]=="BLOCKED_NEW_POTENTIAL_EXECUTION_PATHS"
    assert any(x["file"].endswith("crypto_backdoor.py") for x in result["unknown_crypto_apply_calls"])
    assert not result["production_ready"]


def test_missing_source_fails_closed(tmp_path):
    result=audit_stage97_paper_execution(tmp_path)
    assert result["verdict"]=="BLOCKED_UNVERIFIED_SOURCE"
    assert result["mandatory_all_path_independent_risk_verified"] is False


def test_changed_gateway_requires_independent_rereview(tmp_path):
    root=_synthetic_repo(tmp_path)
    gateway=root/"src/nexus_titan/operations/crypto_spot_reviewed_paper.py"
    gateway.write_bytes(gateway.read_bytes().replace(
        b'Opt-in',b'Opt-out',1))
    result=audit_stage97_paper_execution(root)
    assert result["verdict"]=="BLOCKED_SOURCE_DRIFT"
    assert result["pinned_source_match"] is False


def test_changed_stage97_requires_rereview(tmp_path):
    root=_synthetic_repo(tmp_path)
    target=root/"src/nexus_titan/operations/stage97_crypto_paper.py"
    target.write_bytes(target.read_bytes()+b'\n# local drift\n')
    r=audit_stage97_paper_execution(root)
    assert r["pinned_source_match"] is False
    assert r["production_ready"] is False


def test_malformed_additional_crypto_module_fails_closed(tmp_path):
    root=_synthetic_repo(tmp_path)
    bad=root/"src/nexus_titan/operations/crypto_untrusted.py"
    bad.write_text('from .stage97_crypto_paper import CryptoPaperBook\ndef whoops(:\n')
    result=audit_stage97_paper_execution(root)
    assert result["verdict"]=="BLOCKED_UNVERIFIED_SOURCE"


def test_review_order_change_rejected_even_if_source_rehashed(tmp_path):
    root=_synthetic_repo(tmp_path)
    target=root/"src/nexus_titan/operations/crypto_spot_reviewed_paper.py"
    source=target.read_text()
    assert 'review = review_synthetic_crypto_spot_risk(' in source
    target.write_text(source.replace('review = review_synthetic_crypto_spot_risk(',
                                     'review = unexpected_review('))
    result=audit_stage97_paper_execution(root)
    assert result["opt_in_review_before_apply"] is False
    assert result["production_ready"] is False


def test_reflective_bound_method_lookup_is_not_silently_accepted(tmp_path):
    root=_synthetic_repo(tmp_path)
    target=root/"src/nexus_titan/operations/crypto_alias.py"
    target.write_text('from .stage97_crypto_paper import CryptoPaperBook\n'
                      'def resolve(book: CryptoPaperBook):\n'
                      '    return getattr(book, "apply")\n')
    result=audit_stage97_paper_execution(root)
    assert result["verdict"]=="BLOCKED_NEW_POTENTIAL_EXECUTION_PATHS"
    assert any("getattr" in x["call"] for x in result["unknown_crypto_apply_calls"])


def test_module_level_direct_execution_is_inventory_violation(tmp_path):
    root=_synthetic_repo(tmp_path)
    p=root/"src/nexus_titan/operations/crypto_module_side_effect.py"
    p.write_text('from .stage97_crypto_paper import CryptoPaperBook\n'
                 'book.apply(intent, permit, now_epoch=10)\n')
    result=audit_stage97_paper_execution(root)
    assert result["verdict"]=="BLOCKED_NEW_POTENTIAL_EXECUTION_PATHS"
    assert any(x["scope"]=="<module>" for x in result["unknown_crypto_apply_calls"])
