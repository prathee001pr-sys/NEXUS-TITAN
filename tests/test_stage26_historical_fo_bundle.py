"""Stage26 operator-declared CSV bundle regression tests. All data are synthetic."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from nexus_titan.data.historical_fo_bundle import (
    HistoricalBundleDeclaration, HistoricalBundleError,
    HistoricalSnapshotFile, load_declared_historical_option_chain_bundle,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import OptionChainHistoryError
from nexus_titan.data.option_chain_ingest import COLUMNS, OptionChainIngestionError
from nexus_titan.data.sessions import nse_equity_derivatives_baseline


START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")


def _contract(underlying="NIFTY", *, verified=True):
    return PointInTimeContractSpec(
        symbol=underlying + "OPT", underlying=underlying,
        exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1000,
        max_lots_per_trade=10, strike_step=50,
        effective_from=date(2026,11,1), effective_to=date(2026,11,5),
        expiry_date=date(2026,11,5),
        source_reference="test/exchange-contract-claim", source_verified=verified,
    )


def _payload(when, *, underlying="NIFTY", strike="100", ask="5.50", spot="100"):
    fields = []
    for leg in ("CE", "PE"):
        row = {
            "timestamp":when.isoformat(),
            "symbol":underlying+"OPT", "underlying":underlying,
            "expiry_date":"2026-11-05", "strike":strike,
            "option_type":leg, "bid":"5.00", "ask":ask,
            "ltp":"5.25", "volume":"1000", "open_interest":"1500",
            "underlying_spot":spot, "lot_size":"25",
        }
        fields.append(",".join(row[k] for k in COLUMNS))
    return (",".join(COLUMNS)+"\n"+"\n".join(fields)+"\n").encode()


def _fixture(root, *, count=3, underlying="NIFTY"):
    root.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for i in range(count):
        moment = START + timedelta(minutes=i)
        name = f"market_{i:03d}.csv"
        payload = _payload(moment,underlying=underlying)
        (root/name).write_bytes(payload)
        snapshots.append(HistoricalSnapshotFile(
            name,moment,hashlib.sha256(payload).hexdigest()
        ))
    return HistoricalBundleDeclaration(
        dataset_id="research-qa-not-exchange-data",
        underlying=underlying,
        provider_reference="test/synthetic-vendor-claim",
        licence_reference="test/unverified-licence-claim",
        calendar_reference="test/holidays-not-certified",
        contract_reference="test/exchange-contract-claim",
        declared_start=snapshots[0].observed_at,
        declared_end=snapshots[-1].observed_at,
        snapshots=tuple(snapshots),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )


def _run(root, bundle, **kwargs):
    contract=kwargs.pop("contract",_contract(bundle.underlying))
    calendar=kwargs.pop("calendar",nse_equity_derivatives_baseline())
    return load_declared_historical_option_chain_bundle(
        root, declaration=bundle, contract=contract,
        calendar=calendar, **kwargs,
    )


@pytest.mark.parametrize("underlying", ["NIFTY","BANKNIFTY"])
def test_contiguous_contract_window_structurally_accepted_without_promotion(tmp_path,underlying):
    declaration=_fixture(tmp_path,count=3,underlying=underlying)
    out=_run(tmp_path,declaration)
    assert out.preflight.snapshot_count==3
    assert out.preflight.expected_slots==3
    assert out.preflight.underlying==underlying
    assert len(out.history.snapshots)==3
    assert len(out.preflight.source_file_sha256)==3
    assert out.history.approved_for_strategy_promotion is False
    assert out.preflight.source_licence_authenticated is False
    assert out.preflight.exchange_calendar_authenticated is False
    assert out.preflight.exchange_metadata_authenticated is False
    assert out.preflight.real_market_backtest_verified is False
    assert out.preflight.live_orders_transmitted == 0
    assert out.preflight.approved_for_strategy_promotion is False


def test_fake_licensed_vendor_and_owner_review_cannot_grant_authority(tmp_path):
    d=_fixture(tmp_path)
    d=replace(d,dataset_class_claim="LICENSED_EXCHANGE_HISTORY",
              provider_reference="NSE-LICENSED-SUPER-PROVIDER",
              licence_reference="OFFICIAL-OWNER-ATTESTATION",
              source_review_reference="OWNER-SIGNED")
    result=_run(tmp_path,d)
    assert not result.preflight.source_licence_authenticated
    assert not result.preflight.external_vendor_verified
    assert not result.preflight.approved_for_strategy_promotion


def test_file_mutation_detected_by_sha_before_returning_any_history(tmp_path):
    d=_fixture(tmp_path)
    with (tmp_path/d.snapshots[1].filename).open("ab") as handle:
        handle.write(b"forged")
    with pytest.raises(OptionChainIngestionError,match="checksum mismatch"):
        _run(tmp_path,d)


def test_missing_file_fails_closed(tmp_path):
    d=_fixture(tmp_path)
    (tmp_path/d.snapshots[1].filename).unlink()
    with pytest.raises(HistoricalBundleError,match="missing, linked"):
        _run(tmp_path,d)


def test_duplicate_file_name_fails_closed(tmp_path):
    d=_fixture(tmp_path)
    d=replace(d,snapshots=(d.snapshots[0],replace(d.snapshots[1],filename=d.snapshots[0].filename),d.snapshots[2]))
    with pytest.raises(HistoricalBundleError,match="duplicate filename"):
        _run(tmp_path,d)


def test_duplicate_or_reversed_observation_fails_closed(tmp_path):
    d=_fixture(tmp_path)
    for snapshots in (
        (d.snapshots[0],replace(d.snapshots[1],observed_at=d.snapshots[0].observed_at),d.snapshots[2]),
        (d.snapshots[0],d.snapshots[2],d.snapshots[1]),
    ):
        with pytest.raises(HistoricalBundleError,match="duplicate or out-of-order"):
            _run(tmp_path,replace(d,snapshots=snapshots))


def test_missing_internal_minute_rejected_by_full_history_gate(tmp_path):
    d=_fixture(tmp_path)
    d=replace(d,snapshots=(d.snapshots[0],d.snapshots[-1]))
    with pytest.raises(OptionChainHistoryError,match="Missing 1 expected"):
        _run(tmp_path,d)


def test_first_or_last_snapshot_absent_from_claimed_window_rejected(tmp_path):
    d=_fixture(tmp_path)
    for pair in (
        (d.snapshots[1],d.snapshots[2]),
        (d.snapshots[0],d.snapshots[1]),
    ):
        with pytest.raises(HistoricalBundleError,match="First/last snapshots"):
            _run(tmp_path,replace(d,snapshots=pair))


def test_source_rows_outside_exchange_session_rejected(tmp_path):
    d=_fixture(tmp_path,count=1)
    d=replace(d,snapshots=(replace(d.snapshots[0],observed_at=START.replace(hour=8)),),
              declared_start=START.replace(hour=8),declared_end=START.replace(hour=8))
    with pytest.raises(HistoricalBundleError,match="outside supplied exchange"):
        _run(tmp_path,d)


def test_quote_chain_wrong_contract_does_not_escape_existing_quality_gate(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="contract identity"):
        _run(tmp_path,d,contract=_contract("BANKNIFTY"))


def test_operator_marks_contract_verified_false_and_cannot_be_promoted(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="contract identity"):
        _run(tmp_path,d,contract=_contract(verified=False))


def test_source_declared_unsupported_underlying_fails_closed(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="contract identity"):
        _run(tmp_path,replace(d,underlying="FINNIFTY"))


@pytest.mark.parametrize("filename",[
    "../escape.csv","subfolder/snap.csv","/tmp/evil.csv","snap\\break.csv",
    "x.csv/..", "",".hidden.csv","snap.txt",
])
def test_path_traversal_and_unknown_filename_rejected(tmp_path,filename):
    d=_fixture(tmp_path)
    d=replace(d,snapshots=(replace(d.snapshots[0],filename=filename),)+d.snapshots[1:])
    with pytest.raises(HistoricalBundleError,match="plain CSV basenames"):
        _run(tmp_path,d)


def test_symlink_file_rejected(tmp_path):
    d=_fixture(tmp_path)
    linked=tmp_path/"linked.csv"
    linked.symlink_to(tmp_path/d.snapshots[0].filename)
    d=replace(d,snapshots=(replace(d.snapshots[0],filename="linked.csv"),)+d.snapshots[1:])
    with pytest.raises(HistoricalBundleError,match="missing, linked"):
        _run(tmp_path,d)


def test_symlink_root_rejected(tmp_path):
    real=tmp_path/"real"
    d=_fixture(real)
    link=tmp_path/"linkedroot"
    link.symlink_to(real,target_is_directory=True)
    with pytest.raises(HistoricalBundleError,match="non-symlink root"):
        _run(link,d)


@pytest.mark.parametrize("field,value",[
    ("max_files", 2), ("max_file_bytes", 50), ("max_total_bytes", 500),
])
def test_file_or_memory_caps_rejected(tmp_path,field,value):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="limit|budget|exceeds"):
        _run(tmp_path,d,**{field:value})


@pytest.mark.parametrize("field,value",[
    ("max_files",False),("max_files",0),("max_file_bytes",True),
    ("max_total_bytes",-10),("interval_minutes",0),
])
def test_invalid_resource_caps_fail_closed(tmp_path,field,value):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="bounded positive"):
        _run(tmp_path,d,**{field:value})


def test_invalid_sha_declaration_rejected(tmp_path):
    d=_fixture(tmp_path)
    d=replace(d,snapshots=(replace(d.snapshots[0],sha256="xyz"),)+d.snapshots[1:])
    with pytest.raises(HistoricalBundleError,match="invalid declared SHA-256"):
        _run(tmp_path,d)


def test_quote_temporally_mismatched_to_file_entry_is_rejected(tmp_path):
    d=_fixture(tmp_path)
    first=d.snapshots[0]
    d=replace(d,snapshots=(replace(first,observed_at=START+timedelta(seconds=1)),)+d.snapshots[1:],
              declared_start=START+timedelta(seconds=1))
    with pytest.raises((OptionChainIngestionError,OptionChainHistoryError),match="time|integrity"):
        _run(tmp_path,d)


def test_holiday_calendar_blocks_when_claimed_regular_session_is_closed(tmp_path):
    d=_fixture(tmp_path)
    cal=nse_equity_derivatives_baseline(holidays=frozenset({START.date()}))
    with pytest.raises(HistoricalBundleError,match="outside supplied exchange"):
        _run(tmp_path,d,calendar=cal)


def test_invalid_or_inconsistent_metadata_never_converts_to_licence_proof(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="Missing or invalid"):
        _run(tmp_path,replace(d,licence_reference=""))
    with pytest.raises(HistoricalBundleError,match="contract identity"):
        _run(tmp_path,replace(d,contract_reference="forged/contract"))
    with pytest.raises(HistoricalBundleError,match="Invalid dataset_class"):
        _run(tmp_path,replace(d,dataset_class_claim="AUTO_APPROVED"))


def test_read_only_audit_never_modifies_source_file_bytes(tmp_path):
    d=_fixture(tmp_path)
    original={f.name:f.read_bytes() for f in tmp_path.iterdir()}
    a=_run(tmp_path,d)
    b=_run(tmp_path,d)
    assert a==b
    assert original=={f.name:f.read_bytes() for f in tmp_path.iterdir()}


def test_file_snapshots_must_be_immutable_tuple(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="immutable tuple"):
        _run(tmp_path,replace(d,snapshots=list(d.snapshots)))


def test_empty_and_faked_large_history_block(tmp_path):
    d=_fixture(tmp_path)
    with pytest.raises(HistoricalBundleError,match="count is missing"):
        _run(tmp_path,replace(d,snapshots=()))
    with pytest.raises(HistoricalBundleError,match="bounded limit"):
        _run(tmp_path,replace(d,snapshots=d.snapshots*1000))


def _manifest_json(declaration, contract):
    from dataclasses import asdict
    return {
        "dataset_id": declaration.dataset_id,
        "underlying": declaration.underlying,
        "provider_reference": declaration.provider_reference,
        "licence_reference": declaration.licence_reference,
        "calendar_reference": declaration.calendar_reference,
        "contract_reference": declaration.contract_reference,
        "declared_start": declaration.declared_start.isoformat(),
        "declared_end": declaration.declared_end.isoformat(),
        "dataset_class_claim": declaration.dataset_class_claim,
        "source_review_reference": declaration.source_review_reference,
        "declared_holidays": [],
        "snapshots":[
            {"filename":a.filename,"observed_at":a.observed_at.isoformat(),"sha256":a.sha256}
            for a in declaration.snapshots
        ],
        "contract":{
            "symbol":contract.symbol,"underlying":contract.underlying,
            "exchange":contract.exchange,"segment":contract.segment,
            "lot_size":contract.lot_size,"tick_size":contract.tick_size,
            "freeze_quantity":contract.freeze_quantity,
            "effective_from":contract.effective_from.isoformat(),
            "effective_to":contract.effective_to.isoformat(),
            "expiry_date":contract.expiry_date.isoformat(),
            "strike_step":contract.strike_step,
            "max_lots_per_trade":contract.max_lots_per_trade,
            "source_reference":contract.source_reference,
            "source_verified":contract.source_verified,
        },
    }


def _cli(tmp_path, declaration, *, json_override=None):
    import json
    import subprocess
    import sys
    repo=Path(__file__).resolve().parents[1]
    manifest_path=tmp_path/"contract-manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest_json(declaration,_contract(declaration.underlying)))
        if json_override is None else json_override,encoding="utf-8"
    )
    proc=subprocess.run(
        [sys.executable,str(repo/"scripts"/"run_stage26_fo_bundle_preflight.py"),
         "--root",str(tmp_path),"--declaration",str(manifest_path)],
        cwd=repo,capture_output=True,text=True,timeout=30,check=False,
    )
    return proc


def test_real_cli_with_synthetic_snapshots_succeeds_without_claiming_licence(tmp_path):
    import json
    d=_fixture(tmp_path)
    proc=_cli(tmp_path,d)
    assert proc.returncode==0,proc.stdout+"\n"+proc.stderr
    result=json.loads(proc.stdout)
    assert result["snapshot_count"]==3
    assert result["expected_slots"]==3
    assert result["strategy_promotion_allowed"] is False
    assert result["self_declared_licence_or_vendor_authenticated"] is False
    assert result["broker_orders_sent"] == 0


def test_real_cli_blocks_corrupted_manifest_hash(tmp_path):
    import json
    d=_fixture(tmp_path)
    payload=_manifest_json(d,_contract())
    payload["snapshots"][0]["sha256"]="0"*64
    proc=_cli(tmp_path,d,json_override=json.dumps(payload))
    assert proc.returncode==2
    assert "checksum mismatch" in proc.stderr
    assert proc.stdout==""


def test_real_cli_rejects_duplicate_json_fields_instead_of_last_key_winning(tmp_path):
    d=_fixture(tmp_path)
    proc=_cli(tmp_path,d,json_override='{"dataset_id":"x","dataset_id":"overridden"}')
    assert proc.returncode==2
    assert "Duplicate manifest JSON field" in proc.stderr
    assert proc.stdout==""


def test_real_cli_rejects_declaration_with_fake_licence_claim(tmp_path):
    import json
    d=_fixture(tmp_path)
    payload=_manifest_json(d,_contract())
    payload["contract"]["source_verified"]=False
    proc=_cli(tmp_path,d,json_override=json.dumps(payload))
    assert proc.returncode==2
    assert "contract identity" in proc.stderr
