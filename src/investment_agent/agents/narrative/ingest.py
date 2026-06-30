"""Fetch financial headlines for the Narrative agent (Finnhub + TickerTick)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

TICKERTICK_CURATED = "https://api.tickertick.com/feed"
FINNHUB_NEWS = "https://finnhub.io/api/v1/news"


@dataclass
class NewsArticle:
    id: str
    title: str
    summary: str
    url: str
    source: str
    published_at: str = ""
    provider: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}".strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower())[:48] or "article"


def _parse_ts(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            return str(int(value))
    return str(value)


def _fetch_finnhub(category: str, api_key: str, limit: int) -> list[NewsArticle]:
    articles: list[NewsArticle] = []
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                FINNHUB_NEWS,
                params={"category": category, "token": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return articles

    if not isinstance(data, list):
        return articles

    for i, item in enumerate(data[:limit]):
        if not isinstance(item, dict):
            continue
        title = (item.get("headline") or item.get("title") or "").strip()
        if not title:
            continue
        url = (item.get("url") or "").strip()
        summary = (item.get("summary") or "").strip()
        source = (item.get("source") or "Finnhub").strip()
        ts = _parse_ts(item.get("datetime") or item.get("published_at"))
        aid = f"fh-{_slug(title)}-{i}"
        articles.append(
            NewsArticle(
                id=aid,
                title=title,
                summary=summary,
                url=url or f"https://finnhub.io/news/{aid}",
                source=source,
                published_at=ts,
                provider="finnhub",
            )
        )
    return articles


def _fetch_tickertick(query: str, limit: int) -> list[NewsArticle]:
    articles: list[NewsArticle] = []
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                TICKERTICK_CURATED,
                params={"q": query, "n": min(limit, 200)},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return articles

    stories = data if isinstance(data, list) else data.get("stories", data.get("news", []))
    if not isinstance(stories, list):
        return articles

    for i, item in enumerate(stories[:limit]):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        url = (item.get("url") or item.get("link") or "").strip()
        summary = (item.get("description") or item.get("summary") or "").strip()
        source = (item.get("source") or item.get("site") or "TickerTick").strip()
        ts = _parse_ts(item.get("time") or item.get("published"))
        aid = f"tt-{item.get('id', i)}"
        articles.append(
            NewsArticle(
                id=str(aid),
                title=title,
                summary=summary,
                url=url or "https://tickertick.com",
                source=source,
                published_at=ts,
                provider="tickertick",
            )
        )
    return articles


def _dedupe(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen: set[str] = set()
    out: list[NewsArticle] = []
    for a in articles:
        key = a.title.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def fetch_news_articles(
    *,
    region: str = "global",
    finnhub_key: str | None = None,
    max_articles: int = 40,
) -> tuple[list[NewsArticle], list[str]]:
    """Return articles and ingest notes (providers used, errors)."""
    key = (finnhub_key or os.getenv("FINNHUB_API_KEY", "")).strip()
    max_n = int(os.getenv("NEWS_MAX_ARTICLES", str(max_articles)))
    notes: list[str] = []
    collected: list[NewsArticle] = []

    category = "general"
    if region.lower() == "forex":
        category = "forex"
    elif region.lower() in ("crypto",):
        category = "crypto"

    if key:
        fh = _fetch_finnhub(category, key, max_n)
        collected.extend(fh)
        notes.append(f"finnhub:{len(fh)} articles (category={category})")
    else:
        notes.append("finnhub: skipped (no FINNHUB_API_KEY)")

    tt_query = "T:curated"
    if region.lower() == "china":
        tt_query = "(or tt:baba tt:jd tt:china)"
    tt = _fetch_tickertick(tt_query, max_n)
    collected.extend(tt)
    notes.append(f"tickertick:{len(tt)} articles (q={tt_query})")

    merged = _dedupe(collected)[:max_n]
    if not merged:
        notes.append("warning: no articles fetched")
    return merged, notes
