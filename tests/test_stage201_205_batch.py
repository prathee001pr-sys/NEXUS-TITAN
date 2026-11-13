"""Offline data-readiness controls: no market-data authenticity is inferred."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib

import pytest

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.data.historical_fo_bundle import HistoricalBundlePreflight, HistoricalBundleResearchResult
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.stage200_synthetic_no_go_gate import SyntheticNoGoReceipt
from nexus_titan.data.stage201_fo_catalog_inventory import audit_fo_catalog_inventory
from nexus_titan.data.stage202_fo_contract_master_review import audit_fo_contract_master
from nexus_titan.data.stage203_fo_source_integrity import FOSourceFile, audit_fo_source_files
from nexus_titan.data.stage204_fo_temporal_embargo import FOObservationIndex, audit_fo_temporal_embargo
from nexus_titan.data.stage205_fo_data_readiness_gate import evaluate_fo_data_readiness

T0 = datetime(2024, 1, 2, 9, 15, tzinfo=timezone.utc)
DIGEST = 'a' * 64


def catalog_receipt(file_hash: str, *, dataset_id='fixture1', snapshot_count=1):
    pre = HistoricalBundlePreflight(dataset_id, 'NIFTY', snapshot_count, snapshot_count,
                                   T0, T0+timedelta(days=3), (('sample.csv', file_hash),))
    part = HistoricalBundleResearchResult(pre, None)
    return HistoricalCatalogResult((part,), 1, snapshot_count, 1, T0, T0+timedelta(days=3))


def spec():
    return PointInTimeContractSpec(symbol='NIFTY-20240125-C', underlying='NIFTY', exchange='NSE',
                                   segment='OPTIONS', lot_size=50, freeze_quantity=1000,
                                   tick_size=0.05, effective_from=date(2023, 12, 1),
                                   effective_to=date(2024, 1, 25), expiry_date=date(2024, 1, 25),
                                   source_reference='operator/snapshot-01', source_verified=True)


def make_data(tmp_path):
    data = b'timestamp,bid,ask\n2024-01-02T09:15:00+05:30,10,11\n'
    (tmp_path / 'sample.csv').write_bytes(data)
    h = hashlib.sha256(data).hexdigest()
    return h, (FOSourceFile('fixture1','sample.csv',h,len(data)),)


def timeline():
    return (FOObservationIndex('fixture1', T0, 'TRAIN'),
            FOObservationIndex('fixture1', T0+timedelta(minutes=1), 'TRAIN'),
            FOObservationIndex('fixture1', T0+timedelta(days=2), 'HOLDOUT'),
            FOObservationIndex('fixture1', T0+timedelta(days=2,minutes=1), 'HOLDOUT'))


def valid_receipts(tmp_path):
    h, files = make_data(tmp_path)
    return dict(
        inventory=audit_fo_catalog_inventory(catalog_receipt(h)),
        contracts=audit_fo_contract_master((spec(),), asof=date(2024, 1, 2)),
        sources=audit_fo_source_files(tmp_path, files),
        temporal=audit_fo_temporal_embargo(timeline()),
        synthetic_baseline=SyntheticNoGoReceipt(True, DIGEST, ()),
    )


def test_201_valid_structural_receipt(tmp_path):
    r=valid_receipts(tmp_path)['inventory']
    assert r.accepted_structurally and r.snapshot_count==1 and len(r.inventory_sha256)==64
    assert len(r.source_manifest_sha256)==64 and r.underlyings == ('NIFTY',)
    assert not r.external_market_source_verified and not r.historical_coverage_verified and not r.live_trading_authorized


@pytest.mark.parametrize('mutation',[
    lambda c: replace(c, dataset_count=2),
    lambda c: replace(c, snapshot_count=2),
    lambda c: replace(c, unique_contracts=2),
    lambda c: replace(c, first_observed_at=T0+timedelta(days=1)),
    lambda c: replace(c, partitions=()),
    lambda c: replace(c, partitions=(None,)),
    lambda c: replace(c, partitions=c.partitions+c.partitions, dataset_count=2, snapshot_count=2, unique_contracts=1),
    lambda c: replace(c, partitions=(replace(c.partitions[0],preflight=replace(c.partitions[0].preflight,source_file_sha256=(('x.csv','X'*64),))),)),
    lambda c: replace(c, partitions=(replace(c.partitions[0],preflight=replace(c.partitions[0].preflight,underlying='SENSEX')),)),
    lambda c: replace(c, partitions=(replace(c.partitions[0],preflight=replace(c.partitions[0].preflight,dataset_id='../evil')),)),
    lambda c: replace(c, partitions=(replace(c.partitions[0],preflight=replace(c.partitions[0].preflight,first_observed_at=T0+timedelta(days=1))),)),
])
def test_201_rejects_corrupt_receipts(tmp_path, mutation):
    h,_=make_data(tmp_path)
    r=audit_fo_catalog_inventory(mutation(catalog_receipt(h)))
    assert not r.accepted_structurally and not r.inventory_sha256


def test_201_untrusted_input_fail_closed():
    r=audit_fo_catalog_inventory(None)
    assert r.blockers and r.live_trading_authorized is False


def test_202_accepts_valid_nse_contract_only():
    r=audit_fo_contract_master((spec(),),asof=date(2024,1,2))
    assert r.accepted_structurally and len(r.contract_master_sha256)==64
    assert r.official_exchange_circulars_authenticated is False and r.live_trading_authorized is False


@pytest.mark.parametrize('mutation',[
    lambda s: replace(s,exchange='BSE'),
    lambda s: replace(s,underlying='SENSEX'),
    lambda s: replace(s,segment='EQUITY'),
    lambda s: replace(s,source_verified=False),
    lambda s: replace(s,expiry_date=date(2023,12,25)),
    lambda s: replace(s,effective_from=date(2024,1,3)),
    lambda s: replace(s,expiry_date=None),
])
def test_202_rejects_broken_contract(mutation):
    r=audit_fo_contract_master((mutation(spec()),),asof=date(2024,1,2))
    assert not r.accepted_structurally and r.blockers


def test_202_rejects_duplicates_and_wrong_asof():
    assert not audit_fo_contract_master((spec(),spec()),asof=date(2024,1,2)).accepted_structurally
    assert not audit_fo_contract_master((spec(),),asof='2024-01-02').accepted_structurally
    assert not audit_fo_contract_master((),asof=date(2024,1,2)).accepted_structurally


def test_203_reads_real_bytes_but_does_not_authenticate_vendor(tmp_path):
    h,files=make_data(tmp_path)
    r=audit_fo_source_files(tmp_path,files)
    assert r.accepted_byte_integrity and r.file_count==1 and r.dataset_ids==('fixture1',)
    assert len(r.source_sha256)==64 and len(r.source_manifest_sha256)==64
    assert not r.licensed_vendor_authenticated and not r.exchange_source_authenticated


@pytest.mark.parametrize('change',[
    lambda f: replace(f,sha256='0'*64),
    lambda f: replace(f,byte_count=f.byte_count+1),
    lambda f: replace(f,filename='../sample.csv'),
    lambda f: replace(f,filename='abs/path.csv'),
    lambda f: replace(f,filename='sample.csv\x00'),
    lambda f: replace(f,dataset_id='../evil'),
    lambda f: replace(f,byte_count=True),
])
def test_203_rejects_bad_source_declaration(tmp_path,change):
    _,files=make_data(tmp_path)
    r=audit_fo_source_files(tmp_path,(change(files[0]),))
    assert not r.accepted_byte_integrity and r.blockers


def test_203_tamper_and_symlink_rejected(tmp_path):
    _,files=make_data(tmp_path)
    (tmp_path/'sample.csv').write_bytes(b'changed')
    assert not audit_fo_source_files(tmp_path,files).accepted_byte_integrity
    (tmp_path/'sample.csv').unlink()
    (tmp_path/'sample.csv').symlink_to('/etc/hosts')
    assert not audit_fo_source_files(tmp_path,files).accepted_byte_integrity


def test_203_duplicate_and_invalid_limits(tmp_path):
    _,files=make_data(tmp_path)
    assert not audit_fo_source_files(tmp_path,files+files).accepted_byte_integrity
    assert not audit_fo_source_files(tmp_path,files,max_total_bytes=3).accepted_byte_integrity
    assert not audit_fo_source_files(tmp_path,()).accepted_byte_integrity


def test_204_valid_strict_temporal_split():
    r=audit_fo_temporal_embargo(timeline())
    assert r.accepted_structurally and (r.train_count,r.holdout_count)==(2,2)
    assert len(r.temporal_sha256)==64
    assert not r.upstream_feature_leakage_audited and not r.live_trading_authorized
    assert len(r.observation_windows) == 1


@pytest.mark.parametrize('mutate',[
    lambda pts: pts[::-1],
    lambda pts: (pts[0],pts[0],*pts[2:]),
    lambda pts: (pts[0],pts[1],replace(pts[2],observed_at=pts[1].observed_at+timedelta(minutes=1)),pts[3]),
    lambda pts: tuple(replace(p,subset='TRAIN') for p in pts),
    lambda pts: tuple(replace(p,subset='HOLDOUT') for p in pts),
    lambda pts: tuple(replace(p,subset='INVALID') for p in pts),
    lambda pts: (pts[0],replace(pts[1],observed_at=pts[1].observed_at.replace(tzinfo=None)),pts[2],pts[3]),
    lambda pts: (pts[0],pts[1],replace(pts[2],dataset_id='../bad'),pts[3]),
])
def test_204_rejects_leakage_and_bad_timestamps(mutate):
    r=audit_fo_temporal_embargo(mutate(timeline()))
    assert not r.accepted_structurally and r.blockers


def test_204_rejects_invalid_bounds():
    assert not audit_fo_temporal_embargo(timeline(),embargo_minutes=0).accepted_structurally
    assert not audit_fo_temporal_embargo(timeline()[:3]).accepted_structurally
    assert not audit_fo_temporal_embargo(timeline(),embargo_minutes=True).accepted_structurally


def test_205_links_all_receipts_without_live_authorization(tmp_path):
    args=valid_receipts(tmp_path)
    r=evaluate_fo_data_readiness(**args)
    assert r.eligible_for_internal_manual_dataset_review and len(r.linked_evidence_sha256)==64
    assert not r.real_historical_data_verified and not r.real_market_backtest_verified
    assert not r.live_trading_authorized and not r.autonomous_execution_authorized
    assert not r.strategy_promotion_authorized and not r.independent_vendor_authenticated


@pytest.mark.parametrize('field,mutate',[
    ('inventory',lambda r: replace(r,accepted_structurally=False)),
    ('inventory',lambda r: replace(r,source_manifest_sha256='0'*64)),
    ('contracts',lambda r: replace(r,official_exchange_circulars_authenticated=True, accepted_structurally=False)),
    ('contracts',lambda r: replace(r,contract_master_sha256='invalid')),
    ('sources',lambda r: replace(r,source_manifest_sha256='0'*64)),
    ('sources',lambda r: replace(r,dataset_ids=('other',))),
    ('sources',lambda r: replace(r,accepted_byte_integrity=False)),
    ('temporal',lambda r: replace(r,dataset_ids=('other',))),
    ('temporal',lambda r: replace(r,train_count=0)),
    ('synthetic_baseline',lambda r: replace(r,eligible_for_offline_synthetic_review=False)),
    ('synthetic_baseline',lambda r: replace(r,live_trading_authorized=True)),
])
def test_205_blocks_broken_integration(tmp_path,field,mutate):
    args=valid_receipts(tmp_path)
    args[field]=mutate(args[field])
    r=evaluate_fo_data_readiness(**args)
    assert not r.eligible_for_internal_manual_dataset_review and not r.linked_evidence_sha256 and r.blockers


@pytest.mark.parametrize('override',[
    dict(live_requested=True),dict(autonomous_requested=True),dict(promotion_requested=True),
    dict(live_requested=1),dict(promotion_requested=0)
])
def test_205_blocks_permission_requests(tmp_path,override):
    r=evaluate_fo_data_readiness(**valid_receipts(tmp_path),**override)
    assert not r.eligible_for_internal_manual_dataset_review and r.blockers


def test_205_fails_closed_on_forged_input(tmp_path):
    args=valid_receipts(tmp_path)
    args['inventory']=object()
    r=evaluate_fo_data_readiness(**args)
    assert r.blockers and not r.eligible_for_internal_manual_dataset_review


def test_205_rejects_wrong_catalog_underlying(tmp_path):
    args=valid_receipts(tmp_path)
    args['inventory']=replace(args['inventory'],underlyings=('BANKNIFTY',))
    assert not evaluate_fo_data_readiness(**args).eligible_for_internal_manual_dataset_review


def test_205_rejects_temporal_window_outside_catalog(tmp_path):
    args=valid_receipts(tmp_path)
    bad=replace(args['temporal'],observation_windows=(('fixture1',T0.isoformat(),(T0+timedelta(days=9)).isoformat()),))
    args['temporal']=bad
    assert not evaluate_fo_data_readiness(**args).eligible_for_internal_manual_dataset_review


def test_205_rejects_invalid_window_string(tmp_path):
    args=valid_receipts(tmp_path)
    args['inventory']=replace(args['inventory'],observation_windows=(('fixture1','bad','bad'),))
    assert not evaluate_fo_data_readiness(**args).eligible_for_internal_manual_dataset_review
