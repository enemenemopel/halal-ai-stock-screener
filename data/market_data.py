"""
market_data.py
---------------
Kursdaten und einfache Kennzahlen (ATR, Volumen, gleitende Durchschnitte)
über yfinance (kostenlos, kein API-Key nötig).

WICHTIG: Liefert im Fehlerfall None statt erfundener Werte. Aufrufende
Module MÜSSEN None-Werte abfangen und dürfen sie nicht durch Platzhalter
ersetzen (siehe Projektregel: keine erfundenen Daten).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    ticker: str
    ohlcv: Optional[pd.DataFrame] = None      # Daily OHLCV, letzte ~1 Jahr
    last_price: Optional[float] = None
    avg_dollar_volume: Optional[float] = None
    atr: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    error: Optional[str] = None


def _compute_atr(ohlcv: pd.DataFrame, period: int = 14) -> Optional[float]:
    try:
        high, low, close = ohlcv["High"], ohlcv["Low"], ohlcv["Close"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not np.isnan(atr) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("ATR-Berechnung fehlgeschlagen: %s", exc)
        return None


def _ema(series: pd.Series, span: int) -> Optional[float]:
    try:
        val = series.ewm(span=span, adjust=False).mean().iloc[-1]
        return float(val) if not np.isnan(val) else None
    except Exception:  # noqa: BLE001
        return None


def fetch_price_data(ticker: str, period: str = "1y") -> PriceData:
    """Lädt tägliche OHLCV-Daten und leitet Basiskennzahlen ab.

    Gibt bei Fehlern ein PriceData-Objekt mit gesetztem `error` zurück,
    damit die aufrufende Stelle den Ticker sauber überspringen kann.
    """
    try:
        raw = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        if raw is None or raw.empty or len(raw) < 30:
            return PriceData(ticker=ticker, error="Keine ausreichenden Kursdaten verfügbar")

        raw = raw.dropna(subset=["Close", "Volume"])
        last_price = float(raw["Close"].iloc[-1])
        dollar_vol = (raw["Close"] * raw["Volume"]).tail(20).mean()

        return PriceData(
            ticker=ticker,
            ohlcv=raw,
            last_price=last_price,
            avg_dollar_volume=float(dollar_vol) if not np.isnan(dollar_vol) else None,
            atr=_compute_atr(raw),
            ema20=_ema(raw["Close"], 20),
            ema50=_ema(raw["Close"], 50),
            ema200=_ema(raw["Close"], 200),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Fehler beim Laden der Kursdaten für %s: %s", ticker, exc)
        return PriceData(ticker=ticker, error=str(exc))


def fetch_index_data(ticker: str, period: str = "6mo") -> PriceData:
    """Für Marktindizes (^GSPC, ^IXIC, ^VIX) – nutzt dieselbe Logik."""
    return fetch_price_data(ticker, period=period)
