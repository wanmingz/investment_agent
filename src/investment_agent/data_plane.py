"""Fetch all external data before any analysis agent LLM call."""

from __future__ import annotations

from datetime import date

from investment_agent.config import Settings
from investment_agent.data import fetch_fundamentals_snapshot
from investment_agent.inputs import (
    DataPlaneSnapshot,
    MarketsInput,
    NarrativeInput,
    RegimeInput,
)
from investment_agent.market_data import fetch_vol_snapshot
from investment_agent.news.ingest import fetch_news_articles
from investment_agent.news.rag import (
    build_news_retrieval_query,
    format_context_block,
    retrieve_articles,
)


def build_data_plane(
    settings: Settings,
    *,
    as_of: date | None = None,
) -> DataPlaneSnapshot:
    as_of = as_of or date.today()
    region = settings.market_region
    notes: list[str] = []

    query = build_news_retrieval_query(region=region)
    articles, ingest_notes = fetch_news_articles(
        region=region,
        finnhub_key=settings.finnhub_api_key,
        max_articles=settings.news_max_articles,
    )
    retrieved = retrieve_articles(articles, query, top_k=settings.rag_top_k)
    context = format_context_block(retrieved)
    notes.extend(ingest_notes)

    fundamentals = fetch_fundamentals_snapshot(
        [],
        as_of=as_of,
        finnhub_key=settings.finnhub_api_key,
    )
    notes.append(f"fundamentals:{len(fundamentals.rows)} symbols")

    vol = fetch_vol_snapshot()
    if vol.notes:
        notes.append("vol:" + "; ".join(vol.notes[:3]))

    regime_input = RegimeInput(as_of=as_of, region=region)
    narrative_input = NarrativeInput(
        as_of=as_of,
        region=region,
        retrieval_query=query,
        articles_in_corpus=len(articles),
        articles_retrieved=len(retrieved),
        ingest_notes=list(ingest_notes),
        context_block=context,
        retrieved=tuple(retrieved),
    )
    markets_input = MarketsInput(
        as_of=as_of,
        region=region,
        fundamentals=fundamentals,
        vol=vol,
    )

    return DataPlaneSnapshot(
        as_of=as_of,
        region=region,
        regime_input=regime_input,
        narrative_input=narrative_input,
        markets_input=markets_input,
        data_plane_notes=notes,
    )
