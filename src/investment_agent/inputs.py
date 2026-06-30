"""Disjoint input contracts for v2 pipeline agents (no cross-agent fields)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from investment_agent.data.snapshot import FundamentalsSnapshot
from investment_agent.market_data import VolSnapshot
from investment_agent.news.ingest import NewsArticle


@dataclass(frozen=True)
class RegimeInput:
    """Macro/regime lens only — no news, fundamentals, or vol."""

    as_of: date
    region: str


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
