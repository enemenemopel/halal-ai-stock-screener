"""
earnings.py
-----------
Earnings-Termine und -Historie über yfinance (kostenlos).
Analystenschätzungen (EPS/Revenue Estimate) sind bei yfinance nicht immer
vollständig – fehlende Werte werden als None zurückgegeben und dürfen von
aufrufenden Modulen NICHT ersetzt/erfunden werden.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class EarningsInfo:
    ticker: str
    next_earnings_date: Optional[datetime] = None
    days_until_earnings: Optional[int] = None
    last_eps_actual: Optional[float] = None
    last_eps_estimate: Optional[float] = None
    eps_surprise_pct: Optional[float] = None
    error: Optional[str] = None


def fetch_earnings_info(ticker: str) -> EarningsInfo:
    try:
        tk = yf.Ticker(ticker)

        next_date = None
        try:
            cal = tk.calendar
            if isinstance(cal, dict) and cal.get("Earnings Date"):
                dates = cal["Earnings Date"]
                if isinstance(dates, list) and dates:
                    next_date = dates[0]
            elif hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
                next_date = cal.loc["Earnings Date"][0]
        except Exception as exc:  # noqa: BLE001
            logger.info("Kein Earnings-Kalender für %s: %s", ticker, exc)

        days_until = None
        if next_date is not None:
            try:
                if not isinstance(next_date, datetime):
                    next_date = datetime.combine(next_date, datetime.min.time())
                next_date = next_date.replace(tzinfo=timezone.utc) if next_date.tzinfo is None else next_date
                days_until = (next_date - datetime.now(timezone.utc)).days
            except Exception:  # noqa: BLE001
                days_until = None

        last_eps_actual = last_eps_estimate = eps_surprise = None
        try:
            eps_hist = tk.earnings_dates
            if eps_hist is not None and not eps_hist.empty:
                past = eps_hist.dropna(subset=["Reported EPS"]) if "Reported EPS" in eps_hist.columns else None
                if past is not None and not past.empty:
                    row = past.iloc[0]
                    last_eps_actual = float(row.get("Reported EPS")) if row.get("Reported EPS") is not None else None
                    last_eps_estimate = float(row.get("EPS Estimate")) if row.get("EPS Estimate") is not None else None
                    if last_eps_actual is not None and last_eps_estimate not in (None, 0):
                        eps_surprise = round(
                            ((last_eps_actual - last_eps_estimate) / abs(last_eps_estimate)) * 100, 2
                        )
        except Exception as exc:  # noqa: BLE001
            logger.info("Keine Earnings-Historie für %s: %s", ticker, exc)

        return EarningsInfo(
            ticker=ticker,
            next_earnings_date=next_date,
            days_until_earnings=days_until,
            last_eps_actual=last_eps_actual,
            last_eps_estimate=last_eps_estimate,
            eps_surprise_pct=eps_surprise,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Fehler beim Laden der Earnings-Daten für %s: %s", ticker, exc)
        return EarningsInfo(ticker=ticker, error=str(exc))
