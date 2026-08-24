import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.support_resistance import Zone
from analysis.trade_setup import build_long_setup, build_short_setup

CONFIG = {
    "risk": {
        "min_risk_reward": 2.0,
        "atr_stop_multiplier": 1.3,
        "breakout_confirmation_pct": 0.3,
    }
}


def test_long_setup_valid_with_good_rr():
    supports = [Zone(low=95, high=97, kind="SUPPORT", strength="stark", touches=4)]
    resistances = [Zone(low=110, high=112, kind="RESISTANCE", strength="mittel", touches=2),
                   Zone(low=120, high=122, kind="RESISTANCE", strength="schwach", touches=1)]
    setup = build_long_setup(current_price=97, atr=2.0, supports=supports, resistances=resistances, config=CONFIG)
    assert setup.direction == "LONG"
    assert setup.stop_loss < setup.entry_low
    assert setup.tp1 > setup.entry_high


def test_short_setup_valid_with_good_rr():
    supports = [Zone(low=80, high=82, kind="SUPPORT", strength="mittel", touches=2),
                Zone(low=70, high=72, kind="SUPPORT", strength="schwach", touches=1)]
    resistances = [Zone(low=98, high=100, kind="RESISTANCE", strength="stark", touches=4)]
    setup = build_short_setup(current_price=98, atr=2.0, supports=supports, resistances=resistances, config=CONFIG)
    assert setup.direction == "SHORT"
    assert setup.stop_loss > setup.entry_high
    assert setup.tp1 < setup.entry_low


def test_long_setup_invalid_without_supports():
    setup = build_long_setup(current_price=100, atr=2.0, supports=[], resistances=[], config=CONFIG)
    assert setup.valid is False
    assert setup.invalid_reason is not None


def test_rr_calculation_is_consistent():
    supports = [Zone(low=95, high=97, kind="SUPPORT", strength="stark", touches=5)]
    resistances = [Zone(low=115, high=117, kind="RESISTANCE", strength="stark", touches=5)]
    setup = build_long_setup(current_price=97, atr=1.5, supports=supports, resistances=resistances, config=CONFIG)
    entry = (setup.entry_low + setup.entry_high) / 2
    risk = entry - setup.stop_loss
    expected_rr1 = round((setup.tp1 - entry) / risk, 2)
    assert abs(setup.rr1 - expected_rr1) < 0.05  # exakte Übereinstimmung mit interner _rr()-Formel
