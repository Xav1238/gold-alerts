"""News and calendar sources.

Every source fails soft: an error returns [] so one outage never stops a run.
Edit RSS_FEEDS to add or remove feeds.
"""
import calendar
import hashlib
import os
import re
from datetime import datetime

import feedparser
import requests

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gold-alerts/1.0)"}

RSS_FEEDS = {
    "FXStreet": "https://www.fxstreet.com/rss/news",
    "Google News (gold)": "https://news.google.com/rss/search?q=gold+price+OR+XAUUSD+OR+bullion&hl=en-US&gl=US&ceid=US:en",
    "Google News (macro)": "https://news.google.com/rss/search?q=Fed+OR+inflation+OR+%22Treasury+yields%22+OR+%22US+dollar%22&hl=en-US&gl=US&ceid=US:en",
    "Investing.com": "https://www.investing.com/rss/news_11.rss",
}

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

RELEVANT = re.compile(
    r"\b(?:gold|xau|xauusd|bullion|safe[- ]haven|fed|fomc|powell|rate|inflation|cpi|ppi|pce|"
    r"payroll|nfp|jobs|unemployment|treasury|yield|dollar|dxy|usd|central bank|ecb|boe|boj|"
    r"tariff|sanction|war|missile|ceasefire|israel|iran|russia|ukraine|china|geopolitical|"
    r"geopolitics|recession|gdp|oil|opec|trump|shutdown|stimulus|liquidity)s?\b",
    re.I,
)


def story_id(title: str) -> str:
    """Stable id from the normalised headline, so the same story from two feeds dedupes."""
    norm = re.sub(r"[^a-z0-9]", "", title.lower())
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def is_relevant(item: dict) -> bool:
    return bool(RELEVANT.search(item["title"] + " " + item.get("summary", "")))


def fetch_finnhub() -> list:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return []
    items = []
    for category in ("general", "forex"):
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/news",
                params={"category": category, "token": key},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            for n in r.json():
                title = (n.get("headline") or "").strip()
                if not title:
                    continue
                items.append({
                    "id": story_id(title),
                    "title": title,
                    "summary": (n.get("summary") or "")[:300],
                    "source": n.get("source") or "Finnhub",
                    "url": n.get("url") or "",
                    "ts": float(n.get("datetime") or 0),
                })
        except Exception as e:  # noqa: BLE001
            print(f"[finnhub:{category}] failed: {e}")
    return items


def fetch_rss() -> list:
    items = []
    for name, url in RSS_FEEDS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for e in feed.entries[:40]:
                title = (e.get("title") or "").strip()
                if not title:
                    continue
                parsed = e.get("published_parsed") or e.get("updated_parsed")
                ts = float(calendar.timegm(parsed)) if parsed else 0.0
                summary = re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:300]
                items.append({
                    "id": story_id(title),
                    "title": title,
                    "summary": summary.strip(),
                    "source": name,
                    "url": e.get("link", ""),
                    "ts": ts,
                })
        except Exception as e:  # noqa: BLE001
            print(f"[rss:{name}] failed: {e}")
    return items


def fetch_news() -> list:
    return fetch_finnhub() + fetch_rss()


def fetch_calendar() -> list:
    """This week's economic calendar (free ForexFactory-style JSON)."""
    try:
        r = requests.get(CALENDAR_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        events = []
        for e in r.json():
            ts = datetime.fromisoformat(e["date"]).timestamp()
            events.append({
                "id": story_id(f'{e.get("title")}{e.get("date")}{e.get("country")}'),
                "title": e.get("title", ""),
                "country": e.get("country", ""),
                "impact": e.get("impact", ""),
                "forecast": e.get("forecast", ""),
                "previous": e.get("previous", ""),
                "ts": ts,
            })
        return events
    except Exception as e:  # noqa: BLE001
        print(f"[calendar] failed: {e}")
        return []
