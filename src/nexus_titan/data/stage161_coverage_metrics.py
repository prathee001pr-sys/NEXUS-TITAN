"""Stage 161: deterministic one-minute coverage metrics; research only."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class Coverage:
    complete: bool
    expected: int
    observed: int
    missing: int
    unexpected: int
    duplicates: int

def assess_coverage(expected: tuple[datetime, ...], observed: tuple[datetime, ...]) -> Coverage:
    for values in (expected, observed):
        if not isinstance(values, tuple) or any(not isinstance(x, datetime) or x.tzinfo is None or x.utcoffset() is None for x in values):
            raise ValueError('timezone-aware datetime tuples required')
    exp = [x.astimezone(timezone.utc) for x in expected]
    obs = [x.astimezone(timezone.utc) for x in observed]
    if len(exp) != len(set(exp)) or any(b <= a for a,b in zip(exp,exp[1:])):
        raise ValueError('expected timeline must be strictly increasing')
    if any(b < a for a,b in zip(obs,obs[1:])):
        raise ValueError('observed timeline out of order')
    e, o = set(exp), set(obs)
    missing, unexpected, duplicates = len(e-o), len(o-e), len(obs)-len(o)
    return Coverage(bool(e) and not (missing or unexpected or duplicates), len(e), len(obs), missing, unexpected, duplicates)
