"""
trade_setup.py
--------------
Berechnet algorithmisch Entry, Stop-Loss und Take-Profit-Level (TP1-TP3)
auf Basis von Support/Resistance-Zonen, ATR und Setup-Typ. Kein Entry
= aktueller Kurs (siehe Projektregel #14).

Setup-Erkennung (vereinfacht, regelbasiert):
LONG:  Support Bounce | Breakout | Pullback
SHORT: Resistance Rejection | Breakdown | Bearish Pullback
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from analysis.support_resistance import Zone

logger = logging.getLogger(__name__)


@dataclass
class TradeSetup:
    direction: str              # "LONG" | "SHORT"
    setup_type: str
    entry_low: float
    entry_high: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    rr1: float
    rr2: float
    rr3: float
    support_levels: List[float]
    resistance_levels: List[float]
    valid: bool
    invalid_reason: Optional[str] = None


def _rr(entry: float, stop: float, target: float, direction: str) -> float:
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    reward = (target - entry) if direction == "LONG" else (entry - target)
    return round(max(reward, 0) / risk, 2)


def build_long_setup(current_price: float, atr: Optional[float],
                      supports: List[Zone], resistances: List[Zone],
                      config: dict, breakout: bool = False) -> TradeSetup:
    risk_cfg = config["risk"]
    atr = atr or (current_price * 0.02)  # Fallback: 2% falls ATR fehlt, transparent markiert unten

    if breakout and resistances:
        r = resistances[0]
        entry_low = r.high
        entry_high = r.high * (1 + risk_cfg["breakout_confirmation_pct"] / 100)
        setup_type = "Breakout"
        stop_ref = supports[0].high if supports else entry_low - atr * 2
    elif supports:
        s = supports[0]
        entry_low, entry_high = s.low, s.high
        setup_type = "Support Bounce" if current_price <= s.high * 1.02 else "Pullback"
        stop_ref = s.low
    else:
        return TradeSetup(
            direction="LONG", setup_type="Unbekannt", entry_low=0, entry_high=0, stop_loss=0,
            tp1=0, tp2=0, tp3=0, rr1=0, rr2=0, rr3=0, support_levels=[], resistance_levels=[],
            valid=False, invalid_reason="Keine Support-Zone verfügbar",
        )

    entry = round((entry_low + entry_high) / 2, 2)
    stop_loss = round(stop_ref - atr * risk_cfg["atr_stop_multiplier"], 2)

    res_sorted = sorted([r.low for r in resistances if r.low > entry])
    tp1 = res_sorted[0] if len(res_sorted) > 0 else round(entry + atr * 2, 2)
    tp2 = res_sorted[1] if len(res_sorted) > 1 else round(entry + atr * 3.5, 2)
    tp3 = res_sorted[2] if len(res_sorted) > 2 else round(entry + atr * 5, 2)

    rr1, rr2, rr3 = _rr(entry, stop_loss, tp1, "LONG"), _rr(entry, stop_loss, tp2, "LONG"), _rr(entry, stop_loss, tp3, "LONG")

    valid = rr1 >= risk_cfg["min_risk_reward"]
    reason = None if valid else f"R/R für TP1 ({rr1}) unter Mindestwert {risk_cfg['min_risk_reward']}"

    return TradeSetup(
        direction="LONG", setup_type=setup_type, entry_low=entry_low, entry_high=entry_high,
        stop_loss=stop_loss, tp1=tp1, tp2=tp2, tp3=tp3, rr1=rr1, rr2=rr2, rr3=rr3,
        support_levels=[s.low for s in supports[:3]], resistance_levels=[r.low for r in resistances[:3]],
        valid=valid, invalid_reason=reason,
    )


def build_short_setup(current_price: float, atr: Optional[float],
                       supports: List[Zone], resistances: List[Zone],
                       config: dict, breakdown: bool = False) -> TradeSetup:
    risk_cfg = config["risk"]
    atr = atr or (current_price * 0.02)

    if breakdown and supports:
        s = supports[0]
        entry_low = s.low * (1 - risk_cfg["breakout_confirmation_pct"] / 100)
        entry_high = s.low
        setup_type = "Breakdown"
        stop_ref = resistances[0].low if resistances else entry_high + atr * 2
    elif resistances:
        r = resistances[0]
        entry_low, entry_high = r.low, r.high
        setup_type = "Resistance Rejection" if current_price >= r.low * 0.98 else "Bearish Pullback"
        stop_ref = r.high
    else:
        return TradeSetup(
            direction="SHORT", setup_type="Unbekannt", entry_low=0, entry_high=0, stop_loss=0,
            tp1=0, tp2=0, tp3=0, rr1=0, rr2=0, rr3=0, support_levels=[], resistance_levels=[],
            valid=False, invalid_reason="Keine Resistance-Zone verfügbar",
        )

    entry = round((entry_low + entry_high) / 2, 2)
    stop_loss = round(stop_ref + atr * risk_cfg["atr_stop_multiplier"], 2)

    sup_sorted = sorted([s.high for s in supports if s.high < entry], reverse=True)
    tp1 = sup_sorted[0] if len(sup_sorted) > 0 else round(entry - atr * 2, 2)
    tp2 = sup_sorted[1] if len(sup_sorted) > 1 else round(entry - atr * 3.5, 2)
    tp3 = sup_sorted[2] if len(sup_sorted) > 2 else round(entry - atr * 5, 2)

    rr1, rr2, rr3 = _rr(entry, stop_loss, tp1, "SHORT"), _rr(entry, stop_loss, tp2, "SHORT"), _rr(entry, stop_loss, tp3, "SHORT")

    valid = rr1 >= risk_cfg["min_risk_reward"]
    reason = None if valid else f"R/R für TP1 ({rr1}) unter Mindestwert {risk_cfg['min_risk_reward']}"

    return TradeSetup(
        direction="SHORT", setup_type=setup_type, entry_low=entry_low, entry_high=entry_high,
        stop_loss=stop_loss, tp1=tp1, tp2=tp2, tp3=tp3, rr1=rr1, rr2=rr2, rr3=rr3,
        support_levels=[s.low for s in supports[:3]], resistance_levels=[r.low for r in resistances[:3]],
        valid=valid, invalid_reason=reason,
    )
