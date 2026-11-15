"""Stage126: externally declared capture metadata; never authenticate source by assertion."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from hashlib import sha256
import re
from .stage125_nse_option_chain_snapshot import Stage125Snapshot

class Stage126Blocked(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class Stage126CaptureDeclaration:
    file_basename: str
    declared_sha256: str
    captured_at_ist: str | None
    declared_source: str
    rights_status: str = 'UNVERIFIED'
    independent_authentication: bool = False
    live_trading_enabled: bool = False

@dataclass(frozen=True, slots=True)
class Stage126Review:
    raw_sha256: str
    captured_at_ist: str | None
    timestamp_status: str
    source_status: str = 'DECLARED_ONLY_NOT_AUTHENTICATED'
    verdict: str = 'CAPTURE_DECLARATION_ONLY_NO_GO'
    live_trading_enabled: bool = False

def review_stage126(snapshot: Stage125Snapshot, raw: bytes, declaration: Stage126CaptureDeclaration) -> Stage126Review:
    if type(snapshot) is not Stage125Snapshot or type(raw) is not bytes or type(declaration) is not Stage126CaptureDeclaration:
        raise Stage126Blocked('Exact typed inputs required')
    if snapshot.verdict != 'UNVERIFIED_UNTIMESTAMPED_SNAPSHOT_NO_GO' or snapshot.live_trading_enabled is not False:
        raise Stage126Blocked('Unsafe snapshot state')
    if len(raw)>4_000_000 or sha256(raw).hexdigest()!=snapshot.raw_sha256 or declaration.declared_sha256!=snapshot.raw_sha256:
        raise Stage126Blocked('Payload fingerprint mismatch')
    if type(declaration.file_basename) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv',declaration.file_basename):
        raise Stage126Blocked('Unsafe filename')
    if type(declaration.declared_source) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{1,119}',declaration.declared_source):
        raise Stage126Blocked('Invalid declared source')
    if declaration.rights_status!='UNVERIFIED' or declaration.independent_authentication is not False or declaration.live_trading_enabled is not False:
        raise Stage126Blocked('Unsupported verification or trading claim')
    if declaration.captured_at_ist is None:
        return Stage126Review(snapshot.raw_sha256,None,'MISSING_CAPTURE_TIMESTAMP')
    s=declaration.captured_at_ist
    if type(s) is not str or len(s)>40:
        raise Stage126Blocked('Invalid capture timestamp')
    try:
        t=datetime.fromisoformat(s)
    except ValueError as exc:
        raise Stage126Blocked('Invalid capture timestamp') from exc
    if t.tzinfo is None or t.utcoffset()!=timedelta(hours=5,minutes=30) or t.isoformat()!=s or t.microsecond!=0:
        raise Stage126Blocked('Canonical IST timestamp required')
    if t.date()>date.fromisoformat(snapshot.expiry_date):
        raise Stage126Blocked('Capture after declared expiry')
    return Stage126Review(snapshot.raw_sha256,s,'USER_DECLARED_UNVERIFIED_TIMESTAMP')
