import math
import pytest
from nexus_titan.research.market_intelligence import (
    adx, classify_regime, opening_range, order_book_imbalance,
    rate_of_change, realized_volatility, validate_ohlcv, vwap,
)


def test_vwap_is_cumulative_and_zero_volume_is_unavailable():
    got = vwap([11, 12], [9, 10], [10, 11], [0, 10])
    assert got[0] is None
    assert got[1] == pytest.approx(11.0)


def test_roc_and_realized_volatility_have_warmup():
    roc = rate_of_change([100, 101, 102, 103], 2)
    assert roc[:2] == [None, None]
    assert roc[2] == pytest.approx(2.0)
    rv = realized_volatility([100, 101, 102, 103, 104], 2)
    assert rv[:2] == [None, None]
    assert rv[-1] is not None and rv[-1] >= 0


def test_adx_bounded_and_requires_warmup():
    closes = [100 + i for i in range(50)]
    highs = [x + 1 for x in closes]
    lows = [x - 1 for x in closes]
    result = adx(highs, lows, closes, 5)
    assert result[-1] is not None
    assert 0 <= result[-1] <= 100
    assert adx(highs[:8], lows[:8], closes[:8], 5)[-1] is None


def test_opening_range_and_order_book_imbalance():
    assert opening_range([10, 12, 11], [8, 9, 7], 2) == (12, 8)
    assert order_book_imbalance([100, 50], [50, 50]) == pytest.approx(0.2)


def test_regime_returns_unknown_for_insufficient_history():
    snap = classify_regime([100, 101], [102, 103], [99, 100], adx_period=2, volatility_lookback=2)
    assert snap.trend == "UNKNOWN"


def test_ohlcv_rejects_impossible_candle():
    with pytest.raises(ValueError):
        validate_ohlcv([9], [10], [10], [10], [1])

from nexus_titan.research.market_intelligence import (
    calculate_iv_skew, gamma_exposure, summarize_open_interest,
)
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote


def _quote(kind, oi):
    return OptionChainQuote("2026-11-01T10:00:00+05:30", f"NIFTY-{kind}", "NIFTY", "2026-11-05", 22000,
                            kind, 10, 11, 10.5, 100, oi, 22000, 25)


def test_options_oi_change_and_pcr():
    summary = summarize_open_interest([_quote("CE", 1000), _quote("PE", 1500)],
                                      [_quote("CE", 900), _quote("PE", 1300)])
    assert summary.put_call_ratio == pytest.approx(1.5)
    assert summary.call_oi_change == 100
    assert summary.put_oi_change == 200


def test_iv_skew_and_gamma_exposure_are_explicit_proxies():
    assert calculate_iv_skew({21000: 0.22, 22000: 0.18, 23000: 0.16}, 22000, 5) == pytest.approx(0.06)
    assert gamma_exposure(0.001, 100, 25, 22000) > 0
    assert gamma_exposure(0.001, 100, 25, 22000, call_put_sign=-1) < 0
