"""Lexical RAG for Narrative agent context blocks."""

from __future__ import annotations

import os
import re
from investment_agent.agents.narrative.ingest import NewsArticle

_TOKEN = re.compile(r"[a-z0-9]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def build_news_retrieval_query(
    *,
    region: str,
    extra_terms: list[str] | None = None,
) -> str:
    """Region + market-wide terms only (no upstream agent theme names)."""
    parts = [
        region,
        "rates inflation fed ecb policy earnings ai semiconductor energy oil "
        "tariffs geopolitics banking credit equities bonds",
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


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = " ".join((text or "").split())
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def format_context_block(
    articles: list[NewsArticle],
    *,
    max_summary_chars: int = 400,
    max_total_chars: int = 8000,
) -> str:
    lines = ["## Retrieved news context (use ONLY these articles for news-sourced claims)"]
    used = len(lines[0])
    included = 0
    for art in articles:
        summary = _truncate_text(art.summary or "(no summary)", max_summary_chars)
        title = _truncate_text(art.title, 200)
        entry = (
            f"\n[{art.id}] {title}\n"
            f"Source: {art.source} | Published: {art.published_at or 'unknown'}\n"
            f"Summary: {summary}"
        )
        if used + len(entry) > max_total_chars:
            omitted = len(articles) - included
            if omitted > 0:
                lines.append(
                    f"\n(... {omitted} more articles omitted — "
                    "raise RAG_CONTEXT_MAX_CHARS or lower RAG_TOP_K)"
                )
            break
        lines.append(entry)
        used += len(entry)
        included += 1
    return "\n".join(lines)


def citation_index(articles: list[NewsArticle]) -> dict[str, NewsArticle]:
    return {a.id: a for a in articles}
