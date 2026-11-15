"""Stage 214: read-only independent risk veto over caller-supplied synthetic metrics.

Not a replacement for AuthoritativeRiskEngine, emergency stop or broker risk.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
import hashlib
import json

@dataclass(frozen=True,slots=True)
class VetoPolicy:
    max_drawdown_bps:int
    max_daily_loss_bps:int
    max_open_exposure_bps:int
    max_market_age_ms:int
    require_emergency_stop_clear:bool=True

@dataclass(frozen=True,slots=True)
class VetoSnapshot:
    drawdown_bps:str
    daily_loss_bps:str
    open_exposure_bps:str
    market_age_ms:int
    emergency_stop:bool
    risk_engine_allows_offline_review:bool

@dataclass(frozen=True,slots=True)
class IndependentVetoReceipt:
    eligible_for_offline_risk_review:bool
    veto_sha256:str
    blockers:tuple[str,...]
    independent_runtime_risk_engine_verified:bool=False
    live_trading_authorized:bool=False
    autonomous_execution_authorized:bool=False
    strategy_promotion_authorized:bool=False

def fingerprint_veto_policy(policy:VetoPolicy)->str:
    """Canonical hash of the research risk policy, independent of observed metrics."""
    if type(policy) is not VetoPolicy:
        return ''
    fields={k:getattr(policy,k) for k in policy.__dataclass_fields__}
    if not (all(type(fields[k]) is int for k in ('max_drawdown_bps','max_daily_loss_bps','max_open_exposure_bps','max_market_age_ms'))
            and type(policy.require_emergency_stop_clear) is bool):
        return ''
    return hashlib.sha256(json.dumps(fields,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def audit_independent_risk_veto(policy:VetoPolicy,snapshot:VetoSnapshot,*,
                                live_requested:bool=False,autonomous_requested:bool=False,
                                promotion_requested:bool=False)->IndependentVetoReceipt:
    checks={'typed policy':type(policy) is VetoPolicy,'typed snapshot':type(snapshot) is VetoSnapshot,
            'live prohibited':live_requested is False,
            'autonomous prohibited':autonomous_requested is False,
            'promotion prohibited':promotion_requested is False}
    if type(policy) is VetoPolicy:
        checks.update({'drawdown bound':type(policy.max_drawdown_bps) is int and 0<policy.max_drawdown_bps<=10000,
            'daily loss bound':type(policy.max_daily_loss_bps) is int and 0<policy.max_daily_loss_bps<=10000,
            'exposure bound':type(policy.max_open_exposure_bps) is int and 0<policy.max_open_exposure_bps<=10000,
            'staleness bound':type(policy.max_market_age_ms) is int and 1<=policy.max_market_age_ms<=60000,
            'emergency stop enforcement mandatory':policy.require_emergency_stop_clear is True})
    vals=[]
    if type(snapshot) is VetoSnapshot:
        for name in ('drawdown_bps','daily_loss_bps','open_exposure_bps'):
            s=getattr(snapshot,name)
            try: v=Decimal(s) if type(s) is str else Decimal('NaN')
            except InvalidOperation:v=Decimal('NaN')
            vals.append(v)
        checks['finite nonnegative metrics']=all(v.is_finite() and 0<=v<=100000 for v in vals)
        checks['valid market age']=type(snapshot.market_age_ms) is int and snapshot.market_age_ms>=0
        checks['emergency stop clear']=snapshot.emergency_stop is False
        checks['authoritative offline risk attestation']=snapshot.risk_engine_allows_offline_review is True
        if checks['typed policy'] and len(vals)==3:
            checks['max drawdown observed']=checks['drawdown bound'] and vals[0].is_finite() and vals[0]<=policy.max_drawdown_bps
            checks['daily loss observed']=checks['daily loss bound'] and vals[1].is_finite() and vals[1]<=policy.max_daily_loss_bps
            checks['exposure observed']=checks['exposure bound'] and vals[2].is_finite() and vals[2]<=policy.max_open_exposure_bps
            checks['market freshness observed']=checks['staleness bound'] and checks['valid market age'] and snapshot.market_age_ms<=policy.max_market_age_ms
    blockers=tuple(k for k,ok in checks.items() if not ok)
    digest=hashlib.sha256(json.dumps({'policy':{k:getattr(policy,k) for k in policy.__dataclass_fields__},'snapshot':{k:getattr(snapshot,k) for k in snapshot.__dataclass_fields__}},sort_keys=True,separators=(',',':')).encode()).hexdigest() if not blockers else ''
    return IndependentVetoReceipt(not blockers,digest,blockers)
