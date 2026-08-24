"""
macro_analysis.py
------------------
Bewertet die US-Makro-Datenlage als Score (-100..+100) für die Gesamt-
bewertung. Da kostenlose Quellen i.d.R. keine Forecast-Werte liefern,
basiert die Bewertung primär auf Actual-vs-Previous ("Momentum" der
Datenreihe) statt auf einer echten Forecast-Surprise.

Positive Interpretation (vereinfacht):
- sinkende Inflation (CPI/PCE) -> leicht positiv fürs Marktumfeld
- steigende Beschäftigung (NFP), sinkende Arbeitslosenquote -> positiv
- steigende Treasury Yields / hoher VIX -> eher belastend
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

from data.macro import MacroPoint

logger = logging.getLogger(__name__)

# Vorzeichen-Logik: +1 bedeutet "Anstieg ist positiv fürs Marktregime",
# -1 bedeutet "Anstieg ist negativ fürs Marktregime"
DIRECTION_MAP = {
    "CPI": -1, "CORE_CPI": -1, "PCE": -1, "CORE_PCE": -1,
    "UNEMPLOYMENT": -1, "NFP": +1, "GDP": +1, "RETAIL_SALES": +1,
    "PPI": -1, "FED_FUNDS_RATE": -1, "10Y_TREASURY": -1, "VIX": -1,
}


@dataclass
class MacroAnalysisResult:
    score: float
    available_count: int
    total_count: int
    highlights: List[str]
    note: str = ""


def analyze_macro(snapshot: Dict[str, MacroPoint]) -> MacroAnalysisResult:
    contributions = []
    highlights = []

    for name, point in snapshot.items():
        if not point.available or point.surprise_pct is None:
            continue
        direction = DIRECTION_MAP.get(name, 0)
        contribution = max(min(point.surprise_pct * direction, 20), -20)  # cap pro Indikator
        contributions.append(contribution)
        if abs(point.surprise_pct) >= 1:
            arrow = "↑" if point.surprise_pct > 0 else "↓"
            highlights.append(f"{name} {arrow} {point.surprise_pct:+.1f}% ggü. Vorperiode")

    available_count = len(contributions)
    total_count = len(snapshot)

    if available_count == 0:
        return MacroAnalysisResult(
            score=0.0, available_count=0, total_count=total_count,
            highlights=[], note="Keine Makrodaten verfügbar (FRED_API_KEY prüfen)",
        )

    raw_score = sum(contributions) / available_count
    score = round(max(min(raw_score * 3, 100), -100), 1)  # auf -100..100 skaliert

    note = ""
    if available_count < total_count:
        note = f"Nur {available_count}/{total_count} Makro-Indikatoren verfügbar"

    return MacroAnalysisResult(
        score=score, available_count=available_count, total_count=total_count,
        highlights=highlights[:5], note=note,
    )
