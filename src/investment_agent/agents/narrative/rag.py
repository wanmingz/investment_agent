"""Hybrid RAG (lexical + local embeddings) for Narrative agent context blocks.

Pipeline (called from ``input.build_narrative_input``):
  1. build_news_retrieval_query — fixed macro query (not theme names)
  2. retrieve_articles — score/rank ingest corpus → top-k NewsArticle
  3. format_context_block — stringify top-k into the LLM context_block
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from investment_agent.agents.narrative.ingest import NewsArticle
from investment_agent.config import env_bool, env_int, env_str

if TYPE_CHECKING:
    from investment_agent.config import Settings

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]{3,}")
_EMBEDDING_MODEL: object | None = None


def _tokens(text: str) -> set[str]:
    """Step helper: tokenize for lexical overlap (≥3 alphanumeric chars)."""
    return set(_TOKEN.findall(text.lower()))


def build_news_retrieval_query(
    *,
    region: str,
    extra_terms: list[str] | None = None,
) -> str:
    """Step 1 — Build retrieval query.

    Region + market-wide terms only (no upstream agent theme names), so Narrative
    stays independent of Regime/Markets outputs.
    """
    parts = [
        region,
        "rates inflation fed ecb policy earnings ai semiconductor energy oil "
        "tariffs geopolitics banking credit equities bonds",
    ]
    if extra_terms:
        parts.append(" ".join(extra_terms))
    return " ".join(parts)


def _lexical_scores(
    articles: list[NewsArticle],
    query: str,
) -> list[tuple[float, NewsArticle]]:
    """Step 2a — Lexical rank: token overlap; title hits weighted ×2."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return [(0.0, art) for art in articles]

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
    return scored


def _get_embedding_model(model_name: str):
    """Step 2b helper: lazy-load sentence-transformers once per process (~80MB)."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        _EMBEDDING_MODEL = SentenceTransformer(model_name)
    return _EMBEDDING_MODEL


def _embedding_scores(
    articles: list[NewsArticle],
    query: str,
    *,
    model_name: str,
) -> list[tuple[float, NewsArticle]]:
    """Step 2b — Semantic rank: cosine similarity of normalized embeddings."""
    if not articles:
        return []
    import numpy as np

    model = _get_embedding_model(model_name)
    texts = [art.text for art in articles]
    # Encode query and docs in the same space; higher dot = more similar.
    query_vec = model.encode([query], normalize_embeddings=True)[0]
    doc_vecs = model.encode(texts, normalize_embeddings=True)
    scored: list[tuple[float, NewsArticle]] = []
    for i, art in enumerate(articles):
        sim = float(np.dot(query_vec, doc_vecs[i]))
        scored.append((sim, art))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _rrf_fuse(
    ranked_lists: list[list[NewsArticle]],
    *,
    k: int,
    top_k: int,
) -> list[NewsArticle]:
    """Step 2c — Reciprocal Rank Fusion: merge lexical + embedding rankings.

    Score contribution per list is 1/(k + rank); articles strong in either list rise.
    """
    scores: dict[str, float] = {}
    by_id: dict[str, NewsArticle] = {}
    for ranked in ranked_lists:
        for rank, art in enumerate(ranked, start=1):
            by_id[art.id] = art
            scores[art.id] = scores.get(art.id, 0.0) + 1.0 / (k + rank)
    if not scores:
        return []
    ordered = sorted(scores.keys(), key=lambda aid: scores[aid], reverse=True)
    return [by_id[aid] for aid in ordered[:top_k]]


def retrieve_articles(
    articles: list[NewsArticle],
    query: str,
    *,
    top_k: int | None = None,
    settings: Settings | None = None,
) -> list[NewsArticle]:
    """Step 2 — Retrieve top-k articles from the ingest corpus for ``query``.

    Hybrid path (default): lexical → embedding → RRF fuse.
    If ``RAG_HYBRID=0`` or embeddings fail: lexical-only fallback.
    """
    k = top_k or env_int("RAG_TOP_K", 12)
    if not articles:
        return []

    use_hybrid = settings.rag_hybrid if settings is not None else env_bool("RAG_HYBRID", True)
    model_name = (
        settings.rag_embedding_model
        if settings is not None
        else env_str("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )
    rrf_k = settings.rag_rrf_k if settings is not None else env_int("RAG_RRF_K", 60)

    # Lexical-only mode (no local embedding model).
    if not use_hybrid:
        return _retrieve_lexical_only(articles, query, top_k=k)

    # 2a — lexical ranking
    lex_scored = _lexical_scores(articles, query)
    lex_ranked = [art for _, art in lex_scored] if lex_scored else list(articles)

    try:
        # 2b — embedding ranking
        emb_scored = _embedding_scores(articles, query, model_name=model_name)
        emb_ranked = [art for _, art in emb_scored]
        # 2c — fuse both lists into final top-k
        fused = _rrf_fuse([lex_ranked, emb_ranked], k=rrf_k, top_k=k)
        if fused:
            return fused
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hybrid RAG embedding failed, falling back to lexical: %s", exc)

    return _retrieve_lexical_only(articles, query, top_k=k)


def _retrieve_lexical_only(
    articles: list[NewsArticle],
    query: str,
    *,
    top_k: int,
) -> list[NewsArticle]:
    """Fallback when hybrid is off or embeddings fail: top-k by lexical score."""
    scored = _lexical_scores(articles, query)
    if scored:
        return [a for _, a in scored[:top_k]]
    # No overlap at all — keep ingest order rather than return empty.
    return articles[:top_k]


def _truncate_text(text: str, max_chars: int) -> str:
    """Step 3 helper: collapse whitespace and cap length for the prompt."""
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
    """Step 3 — Format retrieved articles into the Narrative LLM ``context_block``.

    Each entry keeps ``[id]`` for citation; total size capped for provider token limits.
    """
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
        # Stop early if the next article would blow the char budget.
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
    """Lookup helper: article id → NewsArticle (for citation backfill)."""
    return {a.id: a for a in articles}
