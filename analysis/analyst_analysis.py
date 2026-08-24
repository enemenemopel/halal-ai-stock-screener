"""
analyst_analysis.py
--------------------
Bewertet Wall-Street-Analystendaten: nicht nur der aktuelle Konsens zählt,
sondern vor allem die VERÄNDERUNG (Upgrades/Downgrades-Shift) gegenüber
der Vorperiode.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from data.analysts import AnalystInfo

logger = logging.getLogger(__name__)


@dataclass
class AnalystAnalysisResult:
    score: float                # -100..+100
    consensus_label: str        # z.B. "Buy", "Hold", "NICHT VERFÜGBAR"
    shift_description: str
    available: bool
    note: str = ""


def _weighted_consensus(strong_buy, buy, hold, sell, strong_sell) -> Optional[float]:
    """Score von -100 (Strong Sell) bis +100 (Strong Buy)."""
    total = sum(x or 0 for x in [strong_buy, buy, hold, sell, strong_sell])
    if total == 0:
        return None
    weighted = (
        (strong_buy or 0) * 100 + (buy or 0) * 50 + (hold or 0) * 0
        + (sell or 0) * -50 + (strong_sell or 0) * -100
    )
    return weighted / total


def _consensus_label(mean_rating: Optional[float]) -> str:
    if mean_rating is None:
        return "NICHT VERFÜGBAR"
    # yfinance-Skala: 1=Strong Buy, 3=Hold, 5=Strong Sell
    if mean_rating <= 1.5:
        return "Strong Buy"
    if mean_rating <= 2.5:
        return "Buy"
    if mean_rating <= 3.5:
        return "Hold"
    if mean_rating <= 4.5:
        return "Sell"
    return "Strong Sell"


def analyze_analysts(info: AnalystInfo) -> AnalystAnalysisResult:
    if info.error or info.mean_rating is None:
        return AnalystAnalysisResult(
            score=0.0, consensus_label="NICHT VERFÜGBAR", shift_description="",
            available=False, note="Keine Analystendaten verfügbar",
        )

    # Basis-Score aus mean_rating (1..5 -> +100..-100)
    base_score = ((3 - info.mean_rating) / 2) * 100

    shift_description = "Keine Vorperiode verfügbar für Shift-Berechnung"
    shift_bonus = 0.0

    if info.trend_available:
        cur = _weighted_consensus(
            info.current_strong_buy, info.current_buy, info.current_hold,
            info.current_sell, info.current_strong_sell,
        )
        prev = _weighted_consensus(
            info.prev_strong_buy, info.prev_buy, info.prev_hold,
            info.prev_sell, info.prev_strong_sell,
        )
        if cur is not None and prev is not None:
            shift = cur - prev
            shift_bonus = max(min(shift * 0.3, 20), -20)
            direction = "positiver" if shift > 2 else ("negativer" if shift < -2 else "kaum veränderter")
            shift_description = (
                f"{direction} Analysten-Shift ({prev:.0f} → {cur:.0f} auf Konsens-Skala)"
            )

    final_score = round(max(min(base_score + shift_bonus, 100), -100), 1)

    return AnalystAnalysisResult(
        score=final_score,
        consensus_label=_consensus_label(info.mean_rating),
        shift_description=shift_description,
        available=True,
    )
