"""Bounded European Black-Scholes research calculator; not an exchange pricing model."""
from dataclasses import dataclass
from math import erf,exp,log,sqrt,pi,isfinite

@dataclass(frozen=True)
class OptionEstimate:
    price: float
    delta: float
    gamma: float
    vega_per_vol_point: float
    theta_per_day: float
    model: str = 'EUROPEAN_BSM_RESEARCH_ONLY'
    trading_approved: bool = False

def _cdf(x: float) -> float: return 0.5*(1+erf(x/sqrt(2)))
def _pdf(x: float) -> float: return exp(-x*x/2)/sqrt(2*pi)
def estimate_option(*, spot: float, strike: float, years: float, volatility: float, rate: float, side: str, dividend_yield: float=0.0) -> OptionEstimate:
    vals=(spot,strike,years,volatility,rate,dividend_yield)
    if any(not isfinite(float(v)) for v in vals) or spot<=0 or strike<=0 or years<=0 or volatility<=0 or volatility>5 or years>10 or side not in ('CE','PE'):
        raise ValueError('INVALID_MODEL_INPUT')
    root=sqrt(years); d1=(log(spot/strike)+(rate-dividend_yield+volatility**2/2)*years)/(volatility*root); d2=d1-volatility*root
    discount=exp(-rate*years); carry=exp(-dividend_yield*years)
    if side=='CE':
        price=spot*carry*_cdf(d1)-strike*discount*_cdf(d2); delta=carry*_cdf(d1)
    else:
        price=strike*discount*_cdf(-d2)-spot*carry*_cdf(-d1); delta=carry*(_cdf(d1)-1)
    gamma=carry*_pdf(d1)/(spot*volatility*root)
    vega=spot*carry*_pdf(d1)*root/100
    common=-spot*carry*_pdf(d1)*volatility/(2*root)
    theta=(common-rate*strike*discount*_cdf(d2)+dividend_yield*spot*carry*_cdf(d1)) if side=='CE' else (common+rate*strike*discount*_cdf(-d2)-dividend_yield*spot*carry*_cdf(-d1))
    return OptionEstimate(max(0.,price),delta,gamma,vega,theta/365)

def implied_volatility(*, market_price: float, spot: float, strike: float, years: float, rate: float, side: str, dividend_yield: float=0.0, tolerance: float=1e-6) -> float:
    if not isfinite(market_price) or market_price<=0: raise ValueError('INVALID_MARKET_PRICE')
    low,high=0.0001,5.0
    def price(v): return estimate_option(spot=spot,strike=strike,years=years,volatility=v,rate=rate,side=side,dividend_yield=dividend_yield).price
    if market_price < price(low)-tolerance or market_price > price(high)+tolerance: raise ValueError('PRICE_OUTSIDE_MODEL_BOUNDS')
    for _ in range(100):
        mid=(low+high)/2
        if abs(price(mid)-market_price)<=tolerance: return mid
        if price(mid)<market_price: low=mid
        else: high=mid
    return (low+high)/2
