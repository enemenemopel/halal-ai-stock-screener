"""
scoring.py
----------
Kombiniert alle Faktor-Scores (-100..+100 je Faktor) gemäß den in
config.yaml definierten Gewichtungen zu einem finalen LONG- und
SHORT-Score (0..100) sowie einer Confidence-Einstufung.

Fehlende Faktoren werden NICHT durch Fantasiewerte ersetzt, sondern aus
der Gewichtsberechnung herausgerechnet (Renormierung der Gewichte auf die
tatsächlich verfügbaren Faktoren). Das wird transparent vermerkt.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FactorInput:
    name: str                 # "news" | "macro" | "analysts" | "earnings" | "technical" | "volume_momentum"
    score: Optional[float]    # -100..+100, None = nicht verfügbar
    label: str                # kurze Anzeige, z.B. "🟢" / "🔴" / "⚪"


@dataclass
class ScoringResult:
    long_score: float
    short_score: float
    confidence: str            # "HOCH" | "MITTEL" | "NIEDRIG"
    decision: str               # "LONG" | "SHORT" | "NO TRADE"
    factor_summary: List[FactorInput]
    used_weight_pct: float      # wie viel % der Gewichtung tatsächlich mit Daten unterlegt war
    reasons: List[str]


def _emoji(score: Optional[float]) -> str:
    if score is None:
        return "⚪"
    if score >= 15:
        return "🟢"
    if score <= -15:
        return "🔴"
    return "🟡"


def compute_score(factors: Dict[str, Optional[float]], weights: Dict[str, float]) -> ScoringResult:
    """factors: dict mit Keys wie in weights, Werte -100..+100 oder None."""
    total_weight = sum(weights.values())
    available_weight = sum(w for k, w in weights.items() if factors.get(k) is not None)

    if available_weight == 0:
        return ScoringResult(
            long_score=0.0, short_score=0.0, confidence="NIEDRIG", decision="NO TRADE",
            factor_summary=[FactorInput(name=k, score=None, label="⚪") for k in weights],
            used_weight_pct=0.0, reasons=["Keine Datenquelle verfügbar – automatisch NO TRADE"],
        )

    weighted_sum = 0.0
    for key, weight in weights.items():
        val = factors.get(key)
        if val is None:
            continue
        weighted_sum += val * (weight / available_weight)

    # weighted_sum liegt in -100..+100. Long-Score = positiver Anteil, Short-Score = negativer Anteil
    long_score = round(max(weighted_sum, 0), 1)
    short_score = round(max(-weighted_sum, 0), 1)

    # Auf 0..100 skalieren (bereits im Bereich, hier nur Absicherung)
    long_score = min(long_score, 100.0)
    short_score = min(short_score, 100.0)

    used_weight_pct = round((available_weight / total_weight) * 100, 1)

    # Confidence: Übereinstimmung der einzelnen Faktoren in dieselbe Richtung
    signs = [1 if v > 5 else (-1 if v < -5 else 0) for v in factors.values() if v is not None]
    agreement = 0
    if signs:
        dominant_sign = 1 if long_score >= short_score else -1
        agreement = sum(1 for s in signs if s == dominant_sign) / len(signs)

    if used_weight_pct < 50:
        confidence = "NIEDRIG"
    elif agreement >= 0.75 and used_weight_pct >= 70:
        confidence = "HOCH"
    elif agreement >= 0.5:
        confidence = "MITTEL"
    else:
        confidence = "NIEDRIG"

    reasons = []
    decision = "NO TRADE"
    diff = abs(long_score - short_score)

    if used_weight_pct < 40:
        reasons.append(f"Nur {used_weight_pct}% der Gewichtung mit Daten unterlegt – zu wenig Datenbasis")
    elif max(long_score, short_score) < 40:
        reasons.append("Weder Long- noch Short-Score überzeugend stark")
    elif diff < 10:
        reasons.append("Long- und Short-Score zu ähnlich stark – kein klarer Bias")
    else:
        decision = "LONG" if long_score > short_score else "SHORT"

    factor_summary = [
        FactorInput(name=k, score=factors.get(k), label=_emoji(factors.get(k))) for k in weights
    ]

    return ScoringResult(
        long_score=long_score, short_score=short_score, confidence=confidence,
        decision=decision, factor_summary=factor_summary, used_weight_pct=used_weight_pct,
        reasons=reasons,
    )
