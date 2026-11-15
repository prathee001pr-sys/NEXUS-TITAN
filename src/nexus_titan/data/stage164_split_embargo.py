"""Stage 164: enforce chronological train/test split with embargo."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class SplitAudit:
    accepted: bool
    reason: str

def audit_split(*, train_end: datetime, test_start: datetime, embargo_minutes: int) -> SplitAudit:
    if type(embargo_minutes) is not int or embargo_minutes < 0:
        return SplitAudit(False, 'invalid embargo')
    if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in (train_end,test_start)):
        return SplitAudit(False, 'timezone-aware boundaries required')
    if train_end.astimezone(timezone.utc) + timedelta(minutes=embargo_minutes) >= test_start.astimezone(timezone.utc):
        return SplitAudit(False, 'train/test overlap or insufficient embargo')
    return SplitAudit(True, '')
