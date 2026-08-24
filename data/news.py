"""
news.py
-------
Kostenlose Nachrichten-Abfrage über Google-News-RSS (kein API-Key nötig).
Optional zusätzlich NewsAPI, falls NEWSAPI_KEY gesetzt ist (kostenloses
Kontingent, 100 Requests/Tag).

Liefert eine einfache, normalisierte Liste von NewsItem-Objekten.
Keine Sentiment-Bewertung hier – das übernimmt analysis/news_analysis.py.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

import feedparser
import requests

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


@dataclass
class NewsItem:
    title: str
    source: str
    published: Optional[datetime]
    link: str


def _dedupe(items: List[NewsItem]) -> List[NewsItem]:
    """Entfernt doppelte Meldungen (gleicher/sehr ähnlicher Titel)."""
    seen = set()
    unique = []
    for item in items:
        key = item.title.strip().lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def fetch_news_google_rss(query: str, max_items: int = 20) -> List[NewsItem]:
    try:
        url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            items.append(
                NewsItem(
                    title=entry.get("title", "").strip(),
                    source=entry.get("source", {}).get("title", "Google News")
                    if isinstance(entry.get("source"), dict)
                    else "Google News",
                    published=published,
                    link=entry.get("link", ""),
                )
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google-News-RSS Abruf fehlgeschlagen für '%s': %s", query, exc)
        return []


def fetch_news_newsapi(query: str, max_items: int = 20) -> List[NewsItem]:
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_items,
                "apiKey": api_key,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("NewsAPI Status %s: %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        items = []
        for art in data.get("articles", []):
            published = None
            try:
                published = datetime.fromisoformat(art["publishedAt"].replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                pass
            items.append(
                NewsItem(
                    title=art.get("title", ""),
                    source=(art.get("source") or {}).get("name", "NewsAPI"),
                    published=published,
                    link=art.get("url", ""),
                )
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("NewsAPI Abruf fehlgeschlagen für '%s': %s", query, exc)
        return []


def fetch_company_news(company_name: str, ticker: str, max_items: int = 20) -> List[NewsItem]:
    """Kombiniert Google-News-RSS (immer verfügbar) und optional NewsAPI,
    dedupliziert und sortiert nach Aktualität (neueste zuerst)."""
    query = f"{company_name} {ticker} stock"
    items = fetch_news_google_rss(query, max_items) + fetch_news_newsapi(query, max_items)
    items = _dedupe(items)
    items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:max_items]


def fetch_market_news(max_items: int = 15) -> List[NewsItem]:
    """Allgemeine Marktnachrichten (Gesamtmarkt, Fed, Makro)."""
    return _dedupe(fetch_news_google_rss("stock market OR Federal Reserve OR Wall Street", max_items))
