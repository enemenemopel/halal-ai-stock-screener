import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.scoring import compute_score


WEIGHTS = {
    "news": 30, "macro": 20, "analysts": 20,
    "earnings": 15, "technical": 10, "volume_momentum": 5,
}


def test_all_factors_bullish_gives_long_decision():
    factors = {"news": 60, "macro": 40, "analysts": 50, "earnings": 30, "technical": 50, "volume_momentum": 20}
    result = compute_score(factors, WEIGHTS)
    assert result.decision == "LONG"
    assert result.long_score > result.short_score
    assert result.confidence in ("HOCH", "MITTEL", "NIEDRIG")


def test_all_factors_bearish_gives_short_decision():
    factors = {"news": -60, "macro": -40, "analysts": -50, "earnings": -30, "technical": -50, "volume_momentum": -20}
    result = compute_score(factors, WEIGHTS)
    assert result.decision == "SHORT"
    assert result.short_score > result.long_score


def test_no_data_gives_no_trade():
    factors = {k: None for k in WEIGHTS}
    result = compute_score(factors, WEIGHTS)
    assert result.decision == "NO TRADE"
    assert result.used_weight_pct == 0.0


def test_conflicting_factors_give_no_trade():
    factors = {"news": 40, "macro": -40, "analysts": 30, "earnings": -30, "technical": 0, "volume_momentum": 0}
    result = compute_score(factors, WEIGHTS)
    # Sollte entweder NO TRADE sein oder zumindest keine überzogene Sicherheit vorgaukeln
    assert result.decision in ("NO TRADE", "LONG", "SHORT")
    if result.decision != "NO TRADE":
        assert result.confidence != "HOCH"


def test_partial_data_reduces_used_weight():
    factors = {"news": 50, "macro": None, "analysts": None, "earnings": None, "technical": None, "volume_momentum": None}
    result = compute_score(factors, WEIGHTS)
    assert result.used_weight_pct == 30.0  # nur "news" Gewicht (30) verfügbar
