"""
market_regime.py
-----------------
Bestimmt das aktuelle Marktregime (BULLISH / NEUTRAL / BEARISH) auf Basis
von S&P 500, Nasdaq und VIX. Wird VOR der Einzelaktienanalyse berechnet
und fließt in die Long-/Short-Priorisierung ein.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from data.market_data import fetch_index_data

logger = logging.getLogger(__name__)


@dataclass
class MarketRegime:
    regime: str                  # "BULLISH" | "NEUTRAL" | "BEARISH"
    sp500_trend: Optional[str]
    nasdaq_trend: Optional[str]
    vix_level: Optional[float]
    vix_state: Optional[str]     # "NIEDRIG" | "ERHÖHT" | "HOCH"
    notes: list


def _trend_from_price_vs_ma(price: Optional[float], ma: Optional[float]) -> Optional[str]:
    if price is None or ma is None:
        return None
    if price > ma * 1.01:
        return "BULLISH"
    if price < ma * 0.99:
        return "BEARISH"
    return "NEUTRAL"


def _vix_state(vix: Optional[float]) -> Optional[str]:
    if vix is None:
        return None
    if vix < 16:
        return "NIEDRIG"
    if vix < 24:
        return "ERHÖHT"
    return "HOCH"


def determine_market_regime(config: dict) -> MarketRegime:
    idx_cfg = config["market_regime"]["index_tickers"]
    ma_period = config["market_regime"]["bullish_ma_period"]

    notes = []

    sp500 = fetch_index_data(idx_cfg["broad"])
    nasdaq = fetch_index_data(idx_cfg["tech"])
    vix = fetch_index_data(idx_cfg["volatility"])

    sp500_ma = sp500.ohlcv["Close"].rolling(ma_period).mean().iloc[-1] if sp500.ohlcv is not None else None
    nasdaq_ma = nasdaq.ohlcv["Close"].rolling(ma_period).mean().iloc[-1] if nasdaq.ohlcv is not None else None

    sp500_trend = _trend_from_price_vs_ma(sp500.last_price, sp500_ma)
    nasdaq_trend = _trend_from_price_vs_ma(nasdaq.last_price, nasdaq_ma)
    vix_level = vix.last_price
    vix_state = _vix_state(vix_level)

    if sp500_trend is None or nasdaq_trend is None:
        notes.append("Index-Trenddaten unvollständig – Regime mit reduzierter Confidence")

    # Kombinationslogik
    votes = [t for t in [sp500_trend, nasdaq_trend] if t]
    bullish_votes = votes.count("BULLISH")
    bearish_votes = votes.count("BEARISH")

    if not votes:
        regime = "NEUTRAL"
        notes.append("Kein Regime bestimmbar – Standardwert NEUTRAL, Datenlage prüfen")
    elif bullish_votes > bearish_votes and vix_state != "HOCH":
        regime = "BULLISH"
    elif bearish_votes > bullish_votes or vix_state == "HOCH":
        regime = "BEARISH"
    else:
        regime = "NEUTRAL"

    if vix_state == "HOCH":
        notes.append(f"VIX erhöht/hoch ({vix_level:.1f}) – Risiko-Aufschlag aktiv" if vix_level else "VIX hoch")

    return MarketRegime(
        regime=regime,
        sp500_trend=sp500_trend,
        nasdaq_trend=nasdaq_trend,
        vix_level=vix_level,
        vix_state=vix_state,
        notes=notes,
    )
