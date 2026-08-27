"""
main.py
-------
Orchestriert den kompletten Screening-Lauf:
1. Marktregime bestimmen
2. Makro-Snapshot laden
3. Für jede Aktie im Universum:
   a. Liquiditätsfilter
   b. Halal-Filter (vor allem anderen!)
   c. News, Earnings, Analysten, Technik laden
   d. Faktor-Scores berechnen
   e. Long-/Short-Score, Confidence, Entscheidung
   f. Falls LONG/SHORT: Trade-Setup (Entry/SL/TP/RR) berechnen
4. Ranking (Top Long / Top Short)
5. E-Mail zusammenstellen und versenden

Aufruf:
    python main.py --run-type morning
    python main.py --run-type evening
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

import yaml

from analysis.analyst_analysis import analyze_analysts
from analysis.halal_filter import screen_halal
from analysis.macro_analysis import analyze_macro
from analysis.market_regime import determine_market_regime
from analysis.news_analysis import analyze_news
from analysis.scoring import compute_score
from analysis.support_resistance import compute_zones, nearest_zones
from analysis.trade_setup import build_long_setup, build_short_setup
from data.analysts import fetch_analyst_info
from data.earnings import fetch_earnings_info
from data.macro import fetch_macro_snapshot
from data.market_data import fetch_price_data
from data.news import fetch_company_news
from notifications.email import EmailConfigError, EmailSendError, send_report_email
from state import already_sent_today, mark_sent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def analyze_ticker(ticker: str, config: dict, regime) -> dict:
    """Führt die komplette Analyse-Pipeline für einen einzelnen Ticker aus.
    Gibt ein dict mit allen Ergebnissen zurück, oder mit 'skip_reason' wenn
    die Aktie nicht weiter analysiert wird."""

    result = {"ticker": ticker}

    # 1) Preisdaten & Liquiditätsfilter
    price = fetch_price_data(ticker)
    if price.error:
        return {"ticker": ticker, "skip_reason": f"Kursdaten nicht verfügbar: {price.error}"}
    if price.last_price is None or price.last_price < config["universe"]["min_price_usd"]:
        return {"ticker": ticker, "skip_reason": "Kurs unter Mindestpreis"}
    if price.avg_dollar_volume is None or price.avg_dollar_volume < config["universe"]["min_avg_dollar_volume"]:
        return {"ticker": ticker, "skip_reason": "Zu geringe Liquidität"}

    # 2) Halal-Filter (VOR allem anderen)
    halal = screen_halal(ticker, config)
    if halal.status != "HALAL":
        return {
            "ticker": ticker,
            "skip_reason": f"Halal-Status: {halal.status} ({'; '.join(halal.reasons)})",
            "halal": halal,
        }

    # 3) Daten laden: News, Earnings, Analysten
    news_items = fetch_company_news(halal.company_name or ticker, ticker)
    news_result = analyze_news(news_items)

    earnings = fetch_earnings_info(ticker)
    event_risk = "NIEDRIG"
    if earnings.days_until_earnings is not None and 0 <= earnings.days_until_earnings <= 2:
        event_risk = "HOCH"

    analyst_info = fetch_analyst_info(ticker)
    analyst_result = analyze_analysts(analyst_info)

    # 4) Technik: Zonen + einfache Momentum-Bewertung
    zones = compute_zones(price.ohlcv, price.last_price, price.ema20, price.ema50, price.ema200)
    supports = nearest_zones(zones, price.last_price, "SUPPORT")
    resistances = nearest_zones(zones, price.last_price, "RESISTANCE")

    technical_score = None
    if price.ema20 and price.ema50:
        technical_score = 40 if price.last_price > price.ema20 > price.ema50 else (
            -40 if price.last_price < price.ema20 < price.ema50 else 0
        )

    volume_score = None
    try:
        vol_recent = price.ohlcv["Volume"].tail(5).mean()
        vol_avg = price.ohlcv["Volume"].tail(60).mean()
        if vol_avg and vol_avg > 0:
            ratio = vol_recent / vol_avg
            volume_score = max(min((ratio - 1) * 50, 100), -100)
    except Exception:  # noqa: BLE001
        volume_score = None

    earnings_score = None
    if earnings.eps_surprise_pct is not None:
        earnings_score = max(min(earnings.eps_surprise_pct * 4, 100), -100)
    if event_risk == "HOCH":
        earnings_score = (earnings_score or 0) - 20  # Unsicherheit kurz vor Earnings dämpft Score

    # Makroeinfluss ist marktweit -> wird zentral einmal berechnet und übergeben (siehe run())
    macro_score = config.get("_macro_score")

    # Marktregime-Bias
    regime_bias = 15 if regime.regime == "BULLISH" else (-15 if regime.regime == "BEARISH" else 0)
    if technical_score is not None:
        technical_score = max(min(technical_score + regime_bias, 100), -100)

    factors = {
        "news": news_result.score if news_result.available else None,
        "macro": macro_score,
        "analysts": analyst_result.score if analyst_result.available else None,
        "earnings": earnings_score,
        "technical": technical_score,
        "volume_momentum": volume_score,
    }

    scoring = compute_score(factors, config["scoring_weights"])

    if event_risk == "HOCH" and scoring.decision != "NO TRADE":
        scoring.reasons.append("Earnings in ≤2 Tagen -> HIGH EVENT RISK, Setup wird als riskanter markiert")

    setup = None
    if scoring.decision in ("LONG", "SHORT"):
        if scoring.decision == "LONG":
            breakout = bool(resistances) and price.last_price >= resistances[0].low * 0.995
            setup = build_long_setup(price.last_price, price.atr, supports, resistances, config, breakout=breakout)
        else:
            breakdown = bool(supports) and price.last_price <= supports[0].high * 1.005
            setup = build_short_setup(price.last_price, price.atr, supports, resistances, config, breakdown=breakdown)

        if not setup.valid:
            scoring.decision = "NO TRADE"
            scoring.reasons.append(setup.invalid_reason or "Setup ungültig")

    return {
        "ticker": ticker,
        "company_name": halal.company_name,
        "halal": halal,
        "price": price,
        "news": news_result,
        "earnings": earnings,
        "event_risk": event_risk,
        "analyst": analyst_result,
        "scoring": scoring,
        "setup": setup,
        "skip_reason": None,
    }


def build_email_content(results: list, regime, macro_available: bool, run_type: str, config: dict) -> tuple:
    longs = sorted(
        [r for r in results if r.get("scoring") and r["scoring"].decision == "LONG"],
        key=lambda r: r["scoring"].long_score, reverse=True,
    )[: config["ranking"]["max_long_setups"]]

    shorts = sorted(
        [r for r in results if r.get("scoring") and r["scoring"].decision == "SHORT"],
        key=lambda r: r["scoring"].short_score, reverse=True,
    )[: config["ranking"]["max_short_setups"]]

    def render_setup_text(r, direction_emoji):
        s, sc, setup = r["scoring"], r["scoring"], r["setup"]
        score_val = sc.long_score if r["scoring"].decision == "LONG" else sc.short_score
        lines = [
            f"### {r['company_name']} ({r['ticker']})",
            f"{direction_emoji} {sc.decision} — {score_val:.0f}/100 — {sc.confidence} CONFIDENCE",
            f"ENTRY: {setup.entry_low:.2f}–{setup.entry_high:.2f} USD ({setup.setup_type})",
            f"SUPPORT: {', '.join(f'{v:.2f}' for v in setup.support_levels) or 'n/a'}",
            f"RESISTANCE: {', '.join(f'{v:.2f}' for v in setup.resistance_levels) or 'n/a'}",
            f"SL: {setup.stop_loss:.2f} USD",
            f"TP1: {setup.tp1:.2f} | TP2: {setup.tp2:.2f} | TP3: {setup.tp3:.2f}",
            f"R/R: 1:{setup.rr1} / 1:{setup.rr2} / 1:{setup.rr3}",
            "Treiber: " + " ".join(f"{f.name}:{f.label}" for f in sc.factor_summary),
        ]
        if r["event_risk"] == "HOCH":
            lines.append("⚠️ EVENT RISK: HOCH (Earnings ≤2 Tage)")
        return "\n".join(lines)

    text_parts = [f"HALAL AI STOCK SCREENER – {run_type.upper()} REPORT",
                  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), ""]

    text_parts.append("=== TOP LONG ===")
    if longs:
        for r in longs:
            text_parts.append(render_setup_text(r, "🟢"))
            text_parts.append("-" * 40)
    else:
        text_parts.append("Keine überzeugenden Long-Setups gefunden (NO TRADE).")

    text_parts.append("")
    text_parts.append("=== TOP SHORT ===")
    if shorts:
        for r in shorts:
            text_parts.append(render_setup_text(r, "🔴"))
            text_parts.append("-" * 40)
    else:
        text_parts.append("Keine überzeugenden Short-Setups gefunden (NO TRADE).")

    text_parts.append("")
    text_parts.append("=== MARKT ===")
    text_parts.append(f"S&P 500 Trend: {regime.sp500_trend or 'n/a'}")
    text_parts.append(f"Nasdaq Trend: {regime.nasdaq_trend or 'n/a'}")
    text_parts.append(f"Marktregime: {regime.regime}")
    text_parts.append(f"VIX: {regime.vix_level:.1f} ({regime.vix_state})" if regime.vix_level else "VIX: n/a")
    if not macro_available:
        text_parts.append("Hinweis: Makrodaten NICHT VERFÜGBAR (FRED_API_KEY prüfen)")

    skipped = [r for r in results if r.get("skip_reason")]
    text_parts.append("")
    text_parts.append(f"Analysiert: {len(results)} | Übersprungen: {len(skipped)} | "
                       f"Long-Setups: {len(longs)} | Short-Setups: {len(shorts)}")

    text_body = "\n".join(text_parts)

    # Einfache HTML-Version (kompakt, siehe Spezifikation Abschnitt 21)
    html_body = "<pre style='font-family:monospace;font-size:14px;'>" + \
        text_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"

    return text_body, html_body, longs, shorts


def run(run_type: str, config_path: str = "config.yaml", state_path: str = "state/last_sent.json") -> int:
    config = load_config(config_path)

    # Verhindert Doppel-Mails, wenn der Workflow mehrfach innerhalb eines
    # Zeitfensters ausgelöst wird (siehe .github/workflows/screener.yml).
    if already_sent_today(state_path, run_type):
        logger.info("Für '%s' wurde heute bereits erfolgreich eine E-Mail verschickt – überspringe Lauf.", run_type)
        return 0

    logger.info("Starte Screening-Lauf (%s)...", run_type)

    regime = determine_market_regime(config)
    logger.info("Marktregime: %s", regime.regime)

    macro_snapshot = fetch_macro_snapshot()
    macro_result = analyze_macro(macro_snapshot)
    config["_macro_score"] = macro_result.score if macro_result.available_count > 0 else None

    results = []
    for ticker in config["universe"]["tickers"]:
        try:
            res = analyze_ticker(ticker, config, regime)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unerwarteter Fehler bei %s", ticker)
            res = {"ticker": ticker, "skip_reason": f"Unerwarteter Fehler: {exc}"}
        results.append(res)
        if res.get("skip_reason"):
            logger.info("%s übersprungen: %s", ticker, res["skip_reason"])
        elif res.get("scoring"):
            logger.info("%s -> %s (Long %.0f / Short %.0f)", ticker, res["scoring"].decision,
                        res["scoring"].long_score, res["scoring"].short_score)

    text_body, html_body, longs, shorts = build_email_content(
        results, regime, macro_result.available_count > 0, run_type, config
    )

    subject_key = "subject_morning" if run_type == "morning" else "subject_evening"
    subject = config["email"][subject_key]

    print(text_body)  # auch in GitHub Actions Logs sichtbar

    try:
        send_report_email(subject, html_body, text_body)
    except (EmailConfigError, EmailSendError) as exc:
        logger.error("E-Mail-Versand fehlgeschlagen: %s", exc)
        return 1

    mark_sent(state_path, run_type)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Halal AI Stock Screener")
    parser.add_argument("--run-type", choices=["morning", "evening"], default="morning")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    exit_code = run(args.run_type, args.config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
