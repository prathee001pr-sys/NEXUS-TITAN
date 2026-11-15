"""Stage 166: causal bar/signal alignment audit (research only)."""
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class AlignmentReceipt:
    accepted: bool
    errors: tuple[str, ...]

def audit_signal_alignment(bars: tuple[datetime, ...], signals: tuple[tuple[datetime, datetime], ...]) -> AlignmentReceipt:
    """Signal pair is (decision_time, last_observation_time)."""
    errors = []
    if not isinstance(bars, tuple) or not bars:
        return AlignmentReceipt(False, ('missing bars',))
    def aware(t):
        return isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() is not None
    if any(not aware(t) for t in bars):
        return AlignmentReceipt(False, ('naive bar timestamp',))
    timeline = tuple(t.astimezone(timezone.utc) for t in bars)
    if any(a >= b for a, b in zip(timeline, timeline[1:])):
        errors.append('bars not strictly increasing')
    if not isinstance(signals, tuple) or not signals:
        errors.append('missing signals')
    else:
        for i, pair in enumerate(signals):
            if not isinstance(pair, tuple) or len(pair) != 2 or not all(aware(t) for t in pair):
                errors.append(f'signal {i}: invalid timestamps')
                continue
            decision, observed = (t.astimezone(timezone.utc) for t in pair)
            if observed > decision:
                errors.append(f'signal {i}: lookahead')
            if observed not in timeline:
                errors.append(f'signal {i}: observation missing from bars')
    return AlignmentReceipt(not errors, tuple(errors))
