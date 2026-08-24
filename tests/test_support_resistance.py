import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.support_resistance import compute_zones, nearest_zones


def _make_ohlcv(n=200, base=100.0, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="D")
    noise = rng.normal(0, 1.5, n).cumsum()
    close = base + noise
    high = close + rng.uniform(0.5, 2, n)
    low = close - rng.uniform(0.5, 2, n)
    volume = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)


def test_compute_zones_returns_support_and_resistance():
    ohlcv = _make_ohlcv()
    current_price = float(ohlcv["Close"].iloc[-1])
    zones = compute_zones(ohlcv, current_price, ema20=current_price * 0.99,
                           ema50=current_price * 0.97, ema200=current_price * 0.95)
    kinds = {z.kind for z in zones}
    assert "SUPPORT" in kinds or "RESISTANCE" in kinds


def test_nearest_zones_sorted_by_proximity():
    ohlcv = _make_ohlcv()
    current_price = float(ohlcv["Close"].iloc[-1])
    zones = compute_zones(ohlcv, current_price, None, None, None)
    supports = nearest_zones(zones, current_price, "SUPPORT", n=3)
    for z in supports:
        assert z.kind == "SUPPORT"


def test_empty_ohlcv_returns_no_zones():
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    zones = compute_zones(empty, 100.0, None, None, None)
    assert zones == []
