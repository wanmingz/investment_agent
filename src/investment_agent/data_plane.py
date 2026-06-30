"""Data Plane: disjoint agent inputs + external fetch before any LLM call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from investment_agent.config import Settings
from investment_agent.data import (
    FundamentalsSnapshot,
    VolSnapshot,
    fetch_fundamentals_snapshot,
    fetch_vol_snapshot,
)
from investment_agent.data.universe import BENCHMARK_SYMBOL
from investment_agent.news.ingest import NewsArticle, fetch_news_articles
from investment_agent.news.rag import (
    build_news_retrieval_query,
    format_context_block,
    retrieve_articles,
)


@dataclass(frozen=True)
class RegimeInput:
    """Macro/regime lens — derived cross-asset context only (no news articles)."""

    as_of: date
    region: str
    macro_context_block: str = ""
    context_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class NarrativeInput:
    """Headline RAG lens only — pre-fetched in Data Plane."""

    as_of: date
    region: str
    retrieval_query: str
    articles_in_corpus: int
    articles_retrieved: int
    ingest_notes: list[str]
    context_block: str
    retrieved: tuple[NewsArticle, ...] = ()


@dataclass(frozen=True)
class MarketsInput:
    """Equity fundamentals + vol lens only — no other agent outputs."""

    as_of: date
    region: str
    fundamentals: FundamentalsSnapshot
    vol: VolSnapshot


@dataclass
class DataPlaneSnapshot:
    """All external fetches for one run; split into disjoint agent inputs."""

    as_of: date
    region: str
    regime_input: RegimeInput
    narrative_input: NarrativeInput
    markets_input: MarketsInput
    data_plane_notes: list[str] = field(default_factory=list)


def _build_regime_context_block(
    *,
    fundamentals: FundamentalsSnapshot,
    vol: VolSnapshot,
    as_of: date,
    region: str,
) -> tuple[str, list[str]]:
    """Compact macro lens block — not the full Markets prompt payloads."""
    notes: list[str] = []
    lines = [
        "## Cross-asset regime context (yfinance — macro lens only)",
        f"As-of: {as_of.isoformat()}",
        f"Region focus: {region}",
        "Use ONLY these figures for quantitative claims in regime_backdrop and themes.",
    ]

    lines.append("\n### Volatility / risk")
    if vol.vix_level is not None:
        lines.append(f"- VIX proxy (^VIX): {vol.vix_level:.2f}")
    else:
        lines.append("- VIX proxy: unavailable")
        notes.append("regime:vix unavailable")
    if vol.vix_20d_change_pct is not None:
        lines.append(f"- VIX 20d change: {vol.vix_20d_change_pct:+.1f}%")
    if vol.sector_vol:
        for label, ann in sorted(vol.sector_vol.items()):
            lines.append(f"- {label} 20d ann. vol: {ann:.1%}")
    if vol.notes:
        lines.append("- Vol fetch notes: " + "; ".join(vol.notes[:4]))

    lines.append("\n### Sector rotation vs benchmark (ETF snapshot)")
    spy = next((r for r in fundamentals.rows if r.symbol == BENCHMARK_SYMBOL), None)
    if spy and spy.price.return_20d_pct is not None:
        lines.append(f"- {BENCHMARK_SYMBOL} 20d return: {spy.price.return_20d_pct:+.1f}%")
    for row in fundamentals.rows:
        if row.symbol == BENCHMARK_SYMBOL:
            continue
        p = row.price
        parts = [f"- {row.label} ({row.symbol})"]
        if p.return_20d_pct is not None:
            parts.append(f"20d={p.return_20d_pct:+.1f}%")
        if p.vs_spy_20d_pct is not None:
            parts.append(f"vs_SPY={p.vs_spy_20d_pct:+.1f}pp")
        if len(parts) > 1:
            lines.append(" ".join(parts))

    if fundamentals.signals:
        lines.append("\n### Rule-based cross-asset hints")
        for s in fundamentals.signals[:8]:
            lines.append(f"- {s}")

    if fundamentals.notes:
        lines.append("\n### Fundamentals data notes")
        for n in fundamentals.notes[:3]:
            lines.append(f"- {n}")

    if not vol.vix_level and not fundamentals.rows:
        notes.append("regime:degraded context (no vol or ETF rows)")
        lines.append("\n(No live market data — use qualitative macro judgment only.)")

    return "\n".join(lines), notes


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

    macro_block, regime_notes = _build_regime_context_block(
        fundamentals=fundamentals,
        vol=vol,
        as_of=as_of,
        region=region,
    )
    notes.extend(regime_notes)

    regime_input = RegimeInput(
        as_of=as_of,
        region=region,
        macro_context_block=macro_block,
        context_notes=tuple(regime_notes),
    )
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
