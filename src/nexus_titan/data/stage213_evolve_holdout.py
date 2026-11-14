"""Stage 213: bounded, strictly causal synthetic research holdout check.

Does not establish leakage-free features, market validity, or generalization.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from decimal import Decimal,InvalidOperation
import hashlib
import json
from .stage211_evolve_candidate import CandidateIntakeReceipt
from .stage212_evolve_review import OfflineReviewReceipt

@dataclass(frozen=True,slots=True)
class ResearchObservation:
    observed_at:datetime
    subset:str
    net_pnl:str

@dataclass(frozen=True,slots=True)
class EvolveHoldoutReceipt:
    eligible_for_offline_research:bool
    evidence_sha256:str
    train_count:int
    holdout_count:int
    holdout_net_pnl:Decimal
    blockers:tuple[str,...]
    real_market_verified:bool=False
    live_trading_authorized:bool=False
    strategy_promotion_authorized:bool=False

def audit_evolve_holdout(points:tuple[ResearchObservation,...],*,candidate:CandidateIntakeReceipt,
                         review:OfflineReviewReceipt,embargo_minutes:int=1440,
                         max_holdout_loss:str='10000')->EvolveHoldoutReceipt:
    checks={'linked Stage211 research candidate':type(candidate) is CandidateIntakeReceipt and candidate.eligible_for_offline_research is True and not candidate.blockers and len(candidate.candidate_sha256)==64,
            'linked Stage212 offline review':type(review) is OfflineReviewReceipt and review.eligible_for_offline_research is True and not review.blockers and len(review.review_sha256)==64,
            'bounded tuples':type(points) is tuple and 4<=len(points)<=10000,
            'valid embargo':type(embargo_minutes) is int and 1<=embargo_minutes<=43200}
    try:
        threshold=Decimal(max_holdout_loss) if type(max_holdout_loss) is str else Decimal('NaN')
    except InvalidOperation: threshold=Decimal('NaN')
    checks['bounded loss threshold']=threshold.is_finite() and threshold>=0 and threshold<=Decimal('100000000')
    times=[]; splits=[]; values=[]
    if checks['bounded tuples']:
        for p in points:
            if type(p) is not ResearchObservation or type(p.subset) is not str or p.subset not in ('TRAIN','HOLDOUT') or not isinstance(p.observed_at,datetime) or p.observed_at.utcoffset() is None or type(p.net_pnl) is not str:
                checks['typed causal observations']=False;break
            try:v=Decimal(p.net_pnl)
            except InvalidOperation: v=Decimal('NaN')
            if not v.is_finite() or abs(v)>Decimal('100000000'):
                checks['finite bounded pnl']=False;break
            times.append(p.observed_at.astimezone(timezone.utc));splits.append(p.subset);values.append(v)
        else:
            checks['typed causal observations']=True
            checks['finite bounded pnl']=True
    if type(points) is tuple and len(times)==len(points) and times:
        train=[t for t,s in zip(times,splits) if s=='TRAIN']
        holdout=[t for t,s in zip(times,splits) if s=='HOLDOUT']
        checks['strictly increasing timestamps']=all(b>a for a,b in zip(times,times[1:]))
        checks['train/holdout sizes']=len(train)>=2 and len(holdout)>=2
        checks['no interleaved holdout']=splits==['TRAIN']*len(train)+['HOLDOUT']*len(holdout)
        checks['holdout embargo']=bool(train and holdout and checks['valid embargo'] and min(holdout)-max(train)>=timedelta(minutes=embargo_minutes))
    train_count=splits.count('TRAIN');holdout_count=splits.count('HOLDOUT')
    held=sum((p for p,s in zip(values,splits) if s=='HOLDOUT'),Decimal(0))
    checks['holdout within loss cap']=bool(checks['bounded loss threshold'] and held>=-threshold and type(points) is tuple and len(values)==len(points))
    blockers=tuple(k for k,ok in checks.items() if not ok)
    digest=hashlib.sha256(json.dumps({'candidate':candidate.candidate_sha256,'review':review.review_sha256,'embargo':embargo_minutes,'loss':str(threshold),'points':[(t.isoformat(),s,str(v)) for t,s,v in zip(times,splits,values)]},sort_keys=True,separators=(',',':')).encode()).hexdigest() if not blockers else ''
    return EvolveHoldoutReceipt(not blockers,digest,train_count if not blockers else 0,holdout_count if not blockers else 0,held if not blockers else Decimal(0),blockers)
