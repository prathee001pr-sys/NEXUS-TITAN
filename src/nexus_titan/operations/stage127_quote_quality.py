"""Stage127: bounded, deterministic structural quote-quality accounting, no market claims."""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from .stage125_nse_option_chain_snapshot import Stage125Snapshot
from .stage126_snapshot_provenance import Stage126Review

class Stage127Blocked(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class Stage127Quality:
    quote_count: int
    strike_count: int
    flagged_quotes: int
    flags: tuple[tuple[str,int], ...]
    incomplete_quotes: int
    usable_for_historical_backtest: bool = False
    live_trading_enabled: bool = False
    verdict: str = 'STRUCTURAL_QUALITY_ONLY_NO_GO'

def review_stage127(snapshot: Stage125Snapshot, provenance: Stage126Review) -> Stage127Quality:
    if type(snapshot) is not Stage125Snapshot or type(provenance) is not Stage126Review or provenance.raw_sha256!=snapshot.raw_sha256:
        raise Stage127Blocked('Snapshot/provenance mismatch')
    if provenance.verdict!='CAPTURE_DECLARATION_ONLY_NO_GO' or snapshot.verdict!='UNVERIFIED_UNTIMESTAMPED_SNAPSHOT_NO_GO' or provenance.live_trading_enabled is not False or snapshot.live_trading_enabled is not False:
        raise Stage127Blocked('Unsafe predecessor state')
    if snapshot.strike_count<=0 or len(snapshot.quotes)!=2*snapshot.strike_count or len(snapshot.quotes)>20002:
        raise Stage127Blocked('Inconsistent quote count')
    strikes={}
    counts=Counter()
    incomplete=flagged=0
    for q in snapshot.quotes:
        if q.side not in ('CE','PE') or q.strike_paise<=0:
            raise Stage127Blocked('Invalid quote identity')
        strikes.setdefault(q.strike_paise,set())
        if q.side in strikes[q.strike_paise]:
            raise Stage127Blocked('Duplicate strike/side')
        strikes[q.strike_paise].add(q.side)
        if q.quote_flags: flagged+=1
        counts.update(q.quote_flags)
        if q.bid_paise is None or q.ask_paise is None or q.open_interest is None or q.volume is None:
            incomplete+=1
        for field in ('bid_paise','ask_paise','ltp_paise','open_interest','volume'):
            value=getattr(q,field)
            if value is not None and (type(value) is not int or value<0 or value>10**13):
                raise Stage127Blocked('Invalid numeric quote')
        if q.bid_paise is not None and q.ask_paise is not None and q.bid_paise>q.ask_paise and 'CROSSED_MARKET' not in q.quote_flags:
            raise Stage127Blocked('Crossed quote flag missing')
    if len(strikes)!=snapshot.strike_count or any(v!={'CE','PE'} for v in strikes.values()):
        raise Stage127Blocked('Incomplete contract side pairing')
    return Stage127Quality(len(snapshot.quotes),snapshot.strike_count,flagged,tuple(sorted(counts.items())),incomplete)
