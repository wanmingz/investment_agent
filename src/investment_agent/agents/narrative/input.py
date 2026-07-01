"""Narrative agent input — headline ingest + lexical RAG."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from investment_agent.agents.narrative.ingest import NewsArticle, fetch_news_articles
from investment_agent.agents.narrative.rag import (
    build_news_retrieval_query,
    format_context_block,
    retrieve_articles,
)
from investment_agent.config import Settings


@dataclass(frozen=True)
class NarrativeInput:
    as_of: date
    region: str
    retrieval_query: str
    articles_in_corpus: int
    articles_retrieved: int
    ingest_notes: list[str]
    context_block: str
    retrieved: tuple[NewsArticle, ...] = ()


def build_narrative_input(
    settings: Settings,
    *,
    as_of: date,
    region: str,
) -> tuple[NarrativeInput, list[str]]:
    query = build_news_retrieval_query(region=region)
    articles, ingest_notes = fetch_news_articles(
        region=region,
        finnhub_key=settings.finnhub_api_key,
        max_articles=settings.news_max_articles,
    )
    retrieved = retrieve_articles(articles, query, top_k=settings.rag_top_k)
    context = format_context_block(
        retrieved,
        max_summary_chars=settings.rag_summary_max_chars,
        max_total_chars=settings.rag_context_max_chars,
    )

    return (
        NarrativeInput(
            as_of=as_of,
            region=region,
            retrieval_query=query,
            articles_in_corpus=len(articles),
            articles_retrieved=len(retrieved),
            ingest_notes=list(ingest_notes),
            context_block=context,
            retrieved=tuple(retrieved),
        ),
        list(ingest_notes),
    )
