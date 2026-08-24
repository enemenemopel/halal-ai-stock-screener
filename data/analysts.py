"""
analysts.py
-----------
Wall-Street-Analysten-Daten über yfinance (kostenlos).
Liefert aktuellen Rating-Konsens, Kursziel und – soweit verfügbar –
die Veränderung gegenüber vorherigen Perioden (Recommendation Trend).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class AnalystInfo:
    ticker: str
    mean_rating: Optional[float] = None       # 1=Strong Buy ... 5=Strong Sell (yfinance-Skala)
    target_mean_price: Optional[float] = None
    current_strong_buy: Optional[int] = None
    current_buy: Optional[int] = None
    current_hold: Optional[int] = None
    current_sell: Optional[int] = None
    current_strong_sell: Optional[int] = None
    prev_strong_buy: Optional[int] = None
    prev_buy: Optional[int] = None
    prev_hold: Optional[int] = None
    prev_sell: Optional[int] = None
    prev_strong_sell: Optional[int] = None
    trend_available: bool = False
    error: Optional[str] = None


def fetch_analyst_info(ticker: str) -> AnalystInfo:
    try:
        tk = yf.Ticker(ticker)
        info = {}
        try:
            info = tk.info or {}
        except Exception as exc:  # noqa: BLE001
            logger.info("Kein .info für %s: %s", ticker, exc)

        result = AnalystInfo(
            ticker=ticker,
            mean_rating=info.get("recommendationMean"),
            target_mean_price=info.get("targetMeanPrice"),
        )

        try:
            trend = tk.recommendations
            if trend is not None and not trend.empty:
                # yfinance liefert i.d.R. Spalten: strongBuy, buy, hold, sell, strongSell
                # sortiert nach Periode (0 = aktuellster Monat, -1 = Monat davor)
                cols = [c for c in ["strongBuy", "buy", "hold", "sell", "strongSell"] if c in trend.columns]
                if len(trend) >= 1 and cols:
                    cur = trend.iloc[0]
                    result.current_strong_buy = int(cur.get("strongBuy", 0) or 0)
                    result.current_buy = int(cur.get("buy", 0) or 0)
                    result.current_hold = int(cur.get("hold", 0) or 0)
                    result.current_sell = int(cur.get("sell", 0) or 0)
                    result.current_strong_sell = int(cur.get("strongSell", 0) or 0)
                if len(trend) >= 2 and cols:
                    prev = trend.iloc[1]
                    result.prev_strong_buy = int(prev.get("strongBuy", 0) or 0)
                    result.prev_buy = int(prev.get("buy", 0) or 0)
                    result.prev_hold = int(prev.get("hold", 0) or 0)
                    result.prev_sell = int(prev.get("sell", 0) or 0)
                    result.prev_strong_sell = int(prev.get("strongSell", 0) or 0)
                    result.trend_available = True
        except Exception as exc:  # noqa: BLE001
            logger.info("Kein Recommendation-Trend für %s: %s", ticker, exc)

        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("Fehler beim Laden der Analystendaten für %s: %s", ticker, exc)
        return AnalystInfo(ticker=ticker, error=str(exc))
