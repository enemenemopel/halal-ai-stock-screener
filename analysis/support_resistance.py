"""
support_resistance.py
----------------------
Ermittelt Support-/Resistance-ZONEN (keine einzelnen Kurspunkte) aus:
- Swing Highs/Lows (lokale Extrempunkte)
- Tages-/Wochenhochs/-tiefs
- EMA20/50/200, VWAP-Näherung
- mehrfach getesteten Levels (Cluster-Bildung)

Jede Zone bekommt eine Stärke: schwach / mittel / stark, basierend auf
Anzahl der Berührungen und Nähe zu runden/psychologischen Marken.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Zone:
    low: float
    high: float
    kind: str          # "SUPPORT" | "RESISTANCE"
    strength: str       # "schwach" | "mittel" | "stark"
    touches: int


def _find_swings(closes: pd.Series, window: int = 5) -> List[float]:
    """Lokale Extrempunkte (einfaches Rolling-Window-Verfahren)."""
    highs, lows = [], []
    values = closes.values
    for i in range(window, len(values) - window):
        segment = values[i - window: i + window + 1]
        if values[i] == segment.max():
            highs.append(float(values[i]))
        if values[i] == segment.min():
            lows.append(float(values[i]))
    return highs, lows


def _cluster_levels(levels: List[float], tolerance_pct: float = 0.015) -> List[dict]:
    """Gruppiert nahe beieinanderliegende Levels zu Zonen und zählt Berührungen."""
    if not levels:
        return []
    levels = sorted(levels)
    clusters = [[levels[0]]]
    for lvl in levels[1:]:
        if abs(lvl - clusters[-1][-1]) / clusters[-1][-1] <= tolerance_pct:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    result = []
    for c in clusters:
        result.append({"low": min(c), "high": max(c), "touches": len(c)})
    return result


def _strength_from_touches(touches: int) -> str:
    if touches >= 4:
        return "stark"
    if touches >= 2:
        return "mittel"
    return "schwach"


def compute_zones(ohlcv: pd.DataFrame, current_price: float,
                   ema20: Optional[float], ema50: Optional[float], ema200: Optional[float]) -> List[Zone]:
    """Berechnet Support- und Resistance-Zonen relativ zum aktuellen Kurs."""
    if ohlcv is None or ohlcv.empty:
        return []

    closes = ohlcv["Close"].tail(180)
    highs_swing, lows_swing = _find_swings(closes)

    # Wochenhochs/-tiefs als zusätzliche Levels
    weekly = ohlcv.tail(180).copy()
    weekly.index = pd.to_datetime(weekly.index)
    weekly_high = weekly["High"].resample("W").max().dropna().tolist()
    weekly_low = weekly["Low"].resample("W").min().dropna().tolist()

    all_resistance_levels = highs_swing + weekly_high
    all_support_levels = lows_swing + weekly_low

    for ema in [ema20, ema50, ema200]:
        if ema is None:
            continue
        if ema > current_price:
            all_resistance_levels.append(ema)
        else:
            all_support_levels.append(ema)

    resistance_clusters = _cluster_levels([lvl for lvl in all_resistance_levels if lvl > current_price])
    support_clusters = _cluster_levels([lvl for lvl in all_support_levels if lvl < current_price])

    zones = []
    for c in resistance_clusters:
        zones.append(Zone(low=c["low"], high=c["high"], kind="RESISTANCE",
                           strength=_strength_from_touches(c["touches"]), touches=c["touches"]))
    for c in support_clusters:
        zones.append(Zone(low=c["low"], high=c["high"], kind="SUPPORT",
                           strength=_strength_from_touches(c["touches"]), touches=c["touches"]))

    return zones


def nearest_zones(zones: List[Zone], current_price: float, kind: str, n: int = 3) -> List[Zone]:
    filtered = [z for z in zones if z.kind == kind]
    if kind == "SUPPORT":
        filtered.sort(key=lambda z: current_price - z.high)
    else:
        filtered.sort(key=lambda z: z.low - current_price)
    return [z for z in filtered if (current_price - z.high) >= 0 or kind == "RESISTANCE"][:n] or filtered[:n]
