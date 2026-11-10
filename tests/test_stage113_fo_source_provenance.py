from dataclasses import replace,FrozenInstanceError
from hashlib import sha256
import pytest
from nexus_titan.operations.stage113_fo_source_provenance import (Stage113Blocked,review_stage113_csv)
from phase02_fixtures import base,contracts,csv_payload,manifest,DAY


def test_good_synthetic_chunk_never_claims_authenticity():
    items,master,m,raw,x,clock,session=base()
    assert x.row_count==6 and x.master_sha256==master.master_sha256
    assert x.raw_sha256==sha256(raw).hexdigest()
    assert x.first_asof_ist.endswith('09:15:00+05:30')
    assert x.last_asof_ist.endswith('09:17:00+05:30')
    assert not x.provider_authenticated and not x.market_data_license_verified
    assert x.verdict.endswith('NO_GO')
    assert review_stage113_csv(master,m,raw)==x
    with pytest.raises(FrozenInstanceError):x.live_trading_enabled=True


def test_non_synthetic_source_stays_unverified():
    items,master,m,raw,x,clock,session=base()
    m=replace(m,source_kind='LOCAL_UNVERIFIED_FILE',rights_status='RIGHTS_UNVERIFIED',
              declared_provider='HYPOTHETICAL_VENDOR')
    data=review_stage113_csv(master,m,raw)
    assert data.source_kind=='LOCAL_UNVERIFIED_FILE'
    assert not data.quote_origin_verified

@pytest.mark.parametrize('field,value',[
 ('dataset_id','bad/foo'),('dataset_id',''),('file_basename','../foo.csv'),
 ('file_basename','a/b.csv'),('file_basename','\\tmp\\evil.csv'),
 ('file_basename','evil.xlsx'),('file_basename','z'*150+'.csv'),
 ('declared_provider','bad provider'),('declared_provider',''),
 ('raw_sha256','invalid'),('raw_sha256','0'*64),('declared_byte_count',False),
 ('declared_byte_count',99),('source_kind','NSE_OFFICIAL'),
 ('rights_status','LICENSED_AND_VERIFIED'),
 ('rights_status','RIGHTS_UNVERIFIED'),('independently_authenticated',True),
 ('redistribution_permitted_verified',True),('live_trading_enabled',True),
 ('recorded_at_ist',f'{DAY}T09:00:00+05:30'),
 ('recorded_at_ist',f'{DAY}T18:00:01+05:30'),
])
def test_unverified_manifest_refused_if_inconsistent_or_deceptive(field,value):
    _,master,m,raw,*rest=base()
    with pytest.raises(Stage113Blocked):review_stage113_csv(master,replace(m,**{field:value}),raw)

@pytest.mark.parametrize('row_mod',[
 lambda x:x.replace(',1000,1005,100,500',',0,1005,100,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1100,1005,100,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1001,1005,100,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1000,1002,100,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1000,1005,-1,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1000,1005,NaN,500',1),
 lambda x:x.replace(',1000,1005,100,500',',1000,1005,100,True',1),
 lambda x:x.replace('2026-11-10T09:15:00+05:30','2026-11-10T09:15:00+00:00',1),
 lambda x:x.replace('2026-11-10T09:15:00+05:30','2026-11-09T09:15:00+05:30',1),
 lambda x:x.replace('2026-11-10T09:15:00+05:30','2026-11-10T09:15:45+05:30',1),
 lambda x:x.replace('NIFTY-2026-11-24-CE-2500000','NIFTY-OTHER',1),
 lambda x:x.replace('bid_paise,ask_paise','ask_paise,bid_paise',1),
 lambda x:x.replace('bid_paise,ask_paise','bid_paise,bid_paise',1),
 lambda x:x.replace(',1000,1005,100,500',',1000,1005,100,500,EXTRA',1),
 lambda x:x+'\x00',
])
def test_bad_csv_refused(row_mod):
    _,master,m,raw,*_=base()
    raw=row_mod(raw.decode()).encode()
    with pytest.raises(Stage113Blocked):review_stage113_csv(master,manifest(raw),raw)


def test_duplicated_quote_rejected():
    _,master,m,raw,*_=base()
    rows=raw.decode().splitlines()
    dup=('\n'.join(rows+[rows[1]])+'\n').encode()
    with pytest.raises(Stage113Blocked):review_stage113_csv(master,manifest(dup),dup)

@pytest.mark.parametrize('raw', [b'\xff\x80',b'a'* (4*1024*1024+1),b'',b'contract_id\n',b'\x00'*55],ids=['invalid-utf8','too-large','empty','wrong-schema','nul-bytes'])
def test_bad_payload_bytes_rejected(raw):
    _,master,m,old,*_=base()
    with pytest.raises(Stage113Blocked):review_stage113_csv(master,manifest(raw),raw)


def test_master_tamper_rejected():
    _,master,m,raw,*_=base()
    with pytest.raises(Stage113Blocked):review_stage113_csv(replace(master,master_sha256='f'*64),m,raw)
    with pytest.raises(Stage113Blocked):review_stage113_csv(replace(master,official_contract_master_verified=True),m,raw)
