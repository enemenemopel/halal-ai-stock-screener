"""
halal_filter.py
----------------
Vereinfachtes, automatisiertes Shariah-Screening in Anlehnung an gängige
Methoden (u.a. AAOIFI-Standard, ähnlich wie bei Musaffa/S&P Islamic Index):

1. Sektor-/Geschäftsmodell-Ausschluss (Alkohol, Glücksspiel, konventionelle
   Banken/Versicherungen, Tabak, Schweinefleisch, Erwachsenenunterhaltung etc.)
2. Finanzielle Kennzahlen-Schwellenwerte:
   - Zinstragende Schulden / Marktkapitalisierung < 33%
   - Zinstragende Wertpapiere & Cash / Marktkapitalisierung < 33%
   - Forderungen / Marktkapitalisierung < 49%

WICHTIG: Dies ist eine automatisierte Näherung auf Basis öffentlich
verfügbarer Finanzdaten – KEINE verbindliche religiöse Auskunft (Fatwa).
Für Anlageentscheidungen mit religiöser Tragweite sollte zusätzlich eine
anerkannte Shariah-Screening-Quelle konsultiert werden (siehe README).

Wenn benötigte Daten fehlen, wird die Aktie NICHT als halal deklariert,
sondern als NICHT VERFÜGBAR markiert und von der weiteren Analyse
ausgeschlossen (Projektregel #26).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class HalalResult:
    ticker: str
    company_name: Optional[str]
    is_halal: Optional[bool]     # None = nicht bestimmbar
    status: str                  # "HALAL" | "NICHT HALAL" | "NICHT VERFÜGBAR"
    reasons: list
    method: str
    checked_at: str
    debt_ratio: Optional[float] = None
    interest_securities_ratio: Optional[float] = None
    receivables_ratio: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


def _get_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return float(numerator) / float(denominator)
    except Exception:  # noqa: BLE001
        return None


def _sector_excluded(sector: str, industry: str, excluded_keywords: list) -> Optional[str]:
    haystack = f"{sector} {industry}".lower()
    for kw in excluded_keywords:
        if kw.lower() in haystack:
            return kw
    return None


def screen_halal(ticker: str, config: dict) -> HalalResult:
    halal_cfg = config["halal_screening"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Halal-Screening: keine Info-Daten für %s: %s", ticker, exc)
        return HalalResult(
            ticker=ticker, company_name=None, is_halal=None, status="NICHT VERFÜGBAR",
            reasons=["Keine Unternehmensdaten abrufbar"], method=halal_cfg["method_name"], checked_at=now,
        )

    company_name = info.get("longName") or info.get("shortName") or ticker
    sector = info.get("sector", "") or ""
    industry = info.get("industry", "") or ""
    market_cap = info.get("marketCap")

    # 1) Sektor-Ausschluss
    excluded_kw = _sector_excluded(sector, industry, halal_cfg["excluded_sectors_keywords"])
    if excluded_kw:
        return HalalResult(
            ticker=ticker, company_name=company_name, is_halal=False, status="NICHT HALAL",
            reasons=[f"Branche ausgeschlossen (Treffer: '{excluded_kw}', Sektor: {sector}/{industry})"],
            method=halal_cfg["method_name"], checked_at=now, sector=sector, industry=industry,
        )

    # 2) Finanzkennzahlen laden
    total_debt = info.get("totalDebt")
    total_cash = info.get("totalCash")
    receivables = None
    try:
        bs = tk.balance_sheet
        if bs is not None and not bs.empty:
            for label in ["Net Receivables", "Receivables"]:
                if label in bs.index:
                    receivables = float(bs.loc[label].iloc[0])
                    break
    except Exception as exc:  # noqa: BLE001
        logger.info("Keine Bilanzdaten (Receivables) für %s: %s", ticker, exc)

    if market_cap is None or total_debt is None or total_cash is None:
        return HalalResult(
            ticker=ticker, company_name=company_name, is_halal=None, status="NICHT VERFÜGBAR",
            reasons=["Marktkapitalisierung, Schulden oder Cash-Position nicht verfügbar"],
            method=halal_cfg["method_name"], checked_at=now, sector=sector, industry=industry,
        )

    debt_ratio = _get_ratio(total_debt, market_cap)
    interest_sec_ratio = _get_ratio(total_cash, market_cap)
    receivables_ratio = _get_ratio(receivables, market_cap)

    reasons = []
    is_halal = True

    if debt_ratio is not None and debt_ratio >= halal_cfg["max_debt_to_marketcap"]:
        is_halal = False
        reasons.append(f"Schulden/Marktkap. {debt_ratio:.1%} ≥ Grenzwert {halal_cfg['max_debt_to_marketcap']:.0%}")

    if interest_sec_ratio is not None and interest_sec_ratio >= halal_cfg["max_interest_securities_to_marketcap"]:
        is_halal = False
        reasons.append(
            f"Cash/Zinspapiere/Marktkap. {interest_sec_ratio:.1%} ≥ Grenzwert "
            f"{halal_cfg['max_interest_securities_to_marketcap']:.0%}"
        )

    if receivables_ratio is not None and receivables_ratio >= halal_cfg["max_receivables_to_marketcap"]:
        is_halal = False
        reasons.append(
            f"Forderungen/Marktkap. {receivables_ratio:.1%} ≥ Grenzwert "
            f"{halal_cfg['max_receivables_to_marketcap']:.0%}"
        )

    if not reasons:
        reasons.append("Alle geprüften Kennzahlen innerhalb der Grenzwerte")

    status = "HALAL" if is_halal else "NICHT HALAL"
    return HalalResult(
        ticker=ticker, company_name=company_name, is_halal=is_halal, status=status,
        reasons=reasons, method=halal_cfg["method_name"], checked_at=now,
        debt_ratio=debt_ratio, interest_securities_ratio=interest_sec_ratio,
        receivables_ratio=receivables_ratio, sector=sector, industry=industry,
    )
