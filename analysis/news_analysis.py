"""
news_analysis.py
-----------------
Bewertet die Nachrichtenlage einer Aktie: Richtung, Stärke, Aktualität und
Glaubwürdigkeit der Quelle. Nutzt VADER-Sentiment (kostenlos, lokal, kein
API-Call nötig) für die Richtungs-/Stärkebewertung von Schlagzeilen.

Ältere Nachrichten werden über einen Zeit-Decay-Faktor abgeschwächt.
Mehrfachmeldungen wurden bereits in data/news.py dedupliziert.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from data.news import NewsItem

logger = logging.getLogger(__name__)

_analyzer = SentimentIntensityAnalyzer()

# Grobe Quellen-Glaubwürdigkeit (1.0 = hoch). Unbekannte Quellen -> 0.6
CREDIBLE_SOURCES = {
    "reuters": 1.0, "bloomberg": 1.0, "wall street journal": 1.0, "wsj": 1.0,
    "cnbc": 0.9, "financial times": 1.0, "barron's": 0.9, "marketwatch": 0.85,
    "yahoo finance": 0.75, "seeking alpha": 0.6, "benzinga": 0.6, "google news": 0.6,
}


@dataclass
class NewsAnalysisResult:
    score: float                # -100 .. +100 (negativ = bearish, positiv = bullish)
    strength: str                # "SCHWACH" | "MITTEL" | "STARK"
    headline_count: int
    top_headlines: List[str]
    available: bool
    note: str = ""


def _credibility(source: str) -> float:
    s = (source or "").lower()
    for key, weight in CREDIBLE_SOURCES.items():
        if key in s:
            return weight
    return 0.6


def _recency_weight(published, now) -> float:
    if published is None:
        return 0.5
    age_hours = max((now - published).total_seconds() / 3600, 0)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.8
    if age_hours <= 72:
        return 0.5
    if age_hours <= 168:
        return 0.25
    return 0.1  # alte Nachrichten beeinflussen kaum noch


def analyze_news(items: List[NewsItem]) -> NewsAnalysisResult:
    if not items:
        return NewsAnalysisResult(
            score=0.0, strength="SCHWACH", headline_count=0, top_headlines=[],
            available=False, note="Keine Nachrichten gefunden",
        )

    now = datetime.now(timezone.utc)
    weighted_scores = []
    total_weight = 0.0

    for item in items:
        vs = _analyzer.polarity_scores(item.title)
        compound = vs["compound"]  # -1 .. +1
        weight = _credibility(item.source) * _recency_weight(item.published, now)
        weighted_scores.append(compound * weight)
        total_weight += weight

    if total_weight == 0:
        avg = 0.0
    else:
        avg = sum(weighted_scores) / total_weight

    score = round(avg * 100, 1)  # skaliert auf -100..100

    abs_score = abs(score)
    if abs_score >= 40:
        strength = "STARK"
    elif abs_score >= 15:
        strength = "MITTEL"
    else:
        strength = "SCHWACH"

    top_headlines = [i.title for i in items[:3]]

    return NewsAnalysisResult(
        score=score, strength=strength, headline_count=len(items),
        top_headlines=top_headlines, available=True,
    )
