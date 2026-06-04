"""Lightweight lexical RAG (no embedding API) for news chunks."""

from __future__ import annotations

import os
import re
from investment_agent.news.ingest import NewsArticle

_TOKEN = re.compile(r"[a-z0-9]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def build_retrieval_query(
    *,
    region: str,
    theme_names: list[str],
    macro_backdrop: str = "",
    extra_terms: list[str] | None = None,
) -> str:
    parts = [
        region,
        "rates inflation fed ecb policy earnings ai semiconductor energy oil",
        macro_backdrop[:500],
        " ".join(theme_names),
    ]
    if extra_terms:
        parts.append(" ".join(extra_terms))
    return " ".join(parts)


def retrieve_articles(
    articles: list[NewsArticle],
    query: str,
    *,
    top_k: int | None = None,
) -> list[NewsArticle]:
    k = top_k or int(os.getenv("RAG_TOP_K", "12"))
    if not articles:
        return []

    q_tokens = _tokens(query)
    if not q_tokens:
        return articles[:k]

    scored: list[tuple[float, NewsArticle]] = []
    for art in articles:
        doc_tokens = _tokens(art.text)
        if not doc_tokens:
            continue
        overlap = len(q_tokens & doc_tokens)
        title_boost = 2 * len(q_tokens & _tokens(art.title))
        score = overlap + title_boost
        if score > 0:
            scored.append((float(score), art))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [a for _, a in scored[:k]]

    # fallback: most recent-looking first N
    return articles[:k]


def format_context_block(articles: list[NewsArticle]) -> str:
    lines = ["## Retrieved news context (use ONLY these articles for news-sourced claims)"]
    for art in articles:
        lines.append(
            f"\n[{art.id}] {art.title}\n"
            f"Source: {art.source} | Published: {art.published_at or 'unknown'}\n"
            f"URL: {art.url}\n"
            f"Summary: {art.summary or '(no summary)'}"
        )
    return "\n".join(lines)


def citation_index(articles: list[NewsArticle]) -> dict[str, NewsArticle]:
    return {a.id: a for a in articles}
