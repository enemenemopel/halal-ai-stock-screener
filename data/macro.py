"""
macro.py
--------
US-Makrodaten über die kostenlose FRED-API (Federal Reserve Economic Data).

Ein FRED_API_KEY ist kostenlos unter https://fred.stlouisfed.org/docs/api/api_key.html
erhältlich. Ist kein Key gesetzt, werden die betroffenen Datenpunkte als
NICHT VERFÜGBAR markiert (kein Fake-Wert, siehe Projektregel #26).

FRED liefert offizielle Ist-Werte (Actual/Previous) zuverlässig. Forecast-
Werte (Konsensschätzungen) sind bei kostenlosen Quellen nicht zuverlässig
verfügbar; falls kein Forecast vorliegt, wird nur Actual vs. Previous
verglichen und das transparent gekennzeichnet.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FRED_SERIES = {
    "CPI": "CPIAUCSL",
    "CORE_CPI": "CPILFESL",
    "PCE": "PCE",
    "CORE_PCE": "PCEPILFE",
    "UNEMPLOYMENT": "UNRATE",
    "NFP": "PAYEMS",
    "GDP": "GDP",
    "RETAIL_SALES": "RSAFS",
    "PPI": "PPIACO",
    "FED_FUNDS_RATE": "FEDFUNDS",
    "10Y_TREASURY": "DGS10",
    "VIX": "VIXCLS",
}


@dataclass
class MacroPoint:
    name: str
    actual: Optional[float]
    previous: Optional[float]
    forecast: Optional[float]  # bei kostenloser Quelle meist None
    surprise_pct: Optional[float]
    available: bool
    note: str = ""


def _fred_latest_two(series_id: str, api_key: str) -> Optional[list]:
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 3,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("FRED Status %s für %s", resp.status_code, series_id)
            return None
        obs = resp.json().get("observations", [])
        values = [float(o["value"]) for o in obs if o.get("value") not in (None, ".")]
        return values if values else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("FRED Abruf fehlgeschlagen für %s: %s", series_id, exc)
        return None


def fetch_macro_indicator(name: str) -> MacroPoint:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return MacroPoint(
            name=name, actual=None, previous=None, forecast=None,
            surprise_pct=None, available=False,
            note="FRED_API_KEY nicht gesetzt – Datenpunkt NICHT VERFÜGBAR",
        )
    series_id = FRED_SERIES.get(name)
    if not series_id:
        return MacroPoint(
            name=name, actual=None, previous=None, forecast=None,
            surprise_pct=None, available=False, note="Unbekannte Serie",
        )
    values = _fred_latest_two(series_id, api_key)
    if not values or len(values) < 2:
        return MacroPoint(
            name=name, actual=None, previous=None, forecast=None,
            surprise_pct=None, available=False, note="Keine Daten von FRED erhalten",
        )
    actual, previous = values[0], values[1]
    surprise = None
    if previous not in (0, None):
        surprise = round(((actual - previous) / abs(previous)) * 100, 2)
    return MacroPoint(
        name=name, actual=actual, previous=previous, forecast=None,
        surprise_pct=surprise, available=True,
        note="Forecast bei kostenloser Quelle nicht verfügbar – nur Actual vs. Previous",
    )


def fetch_macro_snapshot() -> dict:
    """Lädt die wichtigsten Makro-Indikatoren. Fehlende Serien werden
    transparent als nicht verfügbar markiert, nicht ausgelassen."""
    return {name: fetch_macro_indicator(name) for name in FRED_SERIES}
