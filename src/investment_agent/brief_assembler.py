"""Programmatic merge of v2 agent reports into InvestmentBrief (no LLM)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from investment_agent.dates import format_date_iso
from investment_agent.models import (
    AGENT_MARKETS,
    AGENT_NARRATIVE,
    AGENT_REGIME,
    AgentTheme,
    FinalTheme,
    InvestmentBrief,
    MarketsReport,
    NarrativeReport,
    RegimeReport,
    SourcedItem,
    ThemeStage,
    stage_label,
)

_THEME_KEY_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "sector",
        "theme",
        "risk",
        "vol",
        "low",
        "high",
    }
)
_SECTOR_WORDS: dict[str, str] = {
    "tech": "tech",
    "technology": "tech",
    "software": "tech",
    "ai": "tech",
    "cloud": "tech",
    "energy": "energy",
    "oil": "energy",
    "financial": "financials",
    "financials": "financials",
    "bank": "financials",
    "banks": "financials",
    "healthcare": "healthcare",
    "health": "healthcare",
    "consumer": "consumer",
    "industrial": "industrials",
    "industrials": "industrials",
    "utility": "utilities",
    "utilities": "utilities",
    "defensive": "utilities",
    "growth": "growth",
    "value": "value",
    "inflation": "inflation",
    "rates": "rates",
    "disinflation": "disinflation",
}
_BROAD_SECTORS = frozenset({"growth", "value", "rates", "inflation", "disinflation"})
_MERGEABLE_SECTORS = frozenset(
    {
        "tech",
        "energy",
        "financials",
        "healthcare",
        "consumer",
        "industrials",
        "utilities",
        * _BROAD_SECTORS,
    }
)
_SECTOR_PRIORITY = (
    "financials",
    "energy",
    "healthcare",
    "consumer",
    "industrials",
    "utilities",
    "tech",
    "growth",
    "value",
    "rates",
    "inflation",
    "disinflation",
)
_SECTOR_DISPLAY: dict[str, str] = {
    "tech": "Tech",
    "energy": "Energy",
    "financials": "Financials",
    "healthcare": "Healthcare",
    "consumer": "Consumer",
    "industrials": "Industrials",
    "utilities": "Utilities",
    "growth": "Growth",
    "value": "Value",
    "rates": "Rates & Policy",
    "inflation": "Inflation",
    "disinflation": "Disinflation",
}
_TICKER_SECTOR: dict[str, str] = {
    "xlk": "tech",
    "xle": "energy",
    "xlv": "healthcare",
    "xlf": "financials",
    "igv": "tech",
    "xly": "consumer",
    "xli": "industrials",
    "xlu": "utilities",
    "spy": "benchmark",
}


def theme_key(name: str) -> str:
    """Stable id for clustering similar theme titles across agents."""
    raw = name.lower().strip()
    key = _THEME_KEY_RE.sub("-", raw).strip("-")
    return key or "theme"


def _name_tokens(name: str) -> set[str]:
    return {t for t in theme_key(name).split("-") if len(t) > 2 and t not in _STOPWORDS}


def _sector_tags_from_name(name: str) -> set[str]:
    tags: set[str] = set()
    for token in _name_tokens(name):
        if token in _SECTOR_WORDS:
            tags.add(_SECTOR_WORDS[token])
    return tags


def _primary_sector(theme: AgentTheme) -> str | None:
    """Canonical sector for deduplication (theme title beats ticker tags)."""
    name_tags = _sector_tags_from_name(theme.name)
    for sector in _SECTOR_PRIORITY:
        if sector in name_tags:
            return sector
    for raw in theme.tickers_or_sectors:
        for part in re.split(r"[,;/\s]+", str(raw).lower()):
            sym = part.strip().lstrip("$").lower()
            if sym in _TICKER_SECTOR and _TICKER_SECTOR[sym] != "benchmark":
                return _TICKER_SECTOR[sym]
    return None


def _theme_similarity(a: _TaggedTheme, b: _TaggedTheme) -> float:
    if theme_key(a.theme.name) == theme_key(b.theme.name):
        return 1.0
    ta = _name_tokens(a.theme.name)
    tb = _name_tokens(b.theme.name)
    if not ta or not tb:
        word_score = 0.0
    else:
        word_score = len(ta & tb) / len(ta | tb)
    if word_score >= 0.35:
        return word_score
    return word_score


def _cluster_by_similarity(
    items: list[_TaggedTheme], *, threshold: float = 0.35
) -> list[list[_TaggedTheme]]:
    """Cluster themes with no sector tag by title similarity."""
    n = len(items)
    if n == 0:
        return []
    if n == 1:
        return [items]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            if _theme_similarity(items[i], items[j]) >= threshold:
                union(i, j)

    buckets: dict[int, list[_TaggedTheme]] = defaultdict(list)
    for i, item in enumerate(items):
        buckets[find(i)].append(item)
    return list(buckets.values())


def _cluster_tagged(tagged_all: list[_TaggedTheme]) -> list[list[_TaggedTheme]]:
    """One group per sector; non-sector themes clustered by title similarity."""
    by_sector: dict[str | None, list[_TaggedTheme]] = defaultdict(list)
    for item in tagged_all:
        by_sector[_primary_sector(item.theme)].append(item)

    groups: list[list[_TaggedTheme]] = []
    for sector, items in by_sector.items():
        if sector is not None and sector in _MERGEABLE_SECTORS:
            groups.append(items)
        else:
            groups.extend(_cluster_by_similarity(items))
    return groups


def _group_display_name(group: list[_TaggedTheme]) -> str:
    sectors = {_primary_sector(t.theme) for t in group} - {None}
    if len(sectors) == 1:
        sector = next(iter(sectors))
        return _SECTOR_DISPLAY.get(sector, sector.replace("_", " ").title())
    return max(group, key=lambda t: t.theme.confidence).theme.name


def _merge_theses(group: list[_TaggedTheme]) -> str:
    primary = max(group, key=lambda t: t.theme.confidence)
    seen: set[str] = {primary.theme.thesis}
    parts = [primary.theme.thesis]
    for tagged in sorted(group, key=lambda t: t.theme.confidence, reverse=True):
        thesis = tagged.theme.thesis.strip()
        if thesis and thesis not in seen:
            seen.add(thesis)
            parts.append(thesis)
        if len(parts) >= 2:
            break
    return " ".join(parts) if len(parts) > 1 else parts[0]


def _merge_agent_stages(group: list[_TaggedTheme]) -> dict[str, ThemeStage]:
    best: dict[str, tuple[float, ThemeStage]] = {}
    for tagged in group:
        agent = tagged.agent
        conf = tagged.theme.confidence
        if agent not in best or conf > best[agent][0]:
            best[agent] = (conf, tagged.theme.stage)
    return {agent: stage for agent, (_, stage) in best.items()}


@dataclass
class _TaggedTheme:
    theme: AgentTheme
    agent: str


def _collect_tagged(
    regime: RegimeReport,
    narrative: NarrativeReport,
    markets: MarketsReport,
) -> list[_TaggedTheme]:
    out: list[_TaggedTheme] = []
    for th in regime.themes:
        out.append(_TaggedTheme(th, AGENT_REGIME))
    for th in narrative.themes:
        out.append(_TaggedTheme(th, AGENT_NARRATIVE))
    for th in markets.fundamentals_themes:
        out.append(_TaggedTheme(th, AGENT_MARKETS))
    for th in markets.vol_themes:
        out.append(_TaggedTheme(th, AGENT_MARKETS))
    return out


def _pick_stage(tagged: list[_TaggedTheme]) -> ThemeStage:
    primary = max(tagged, key=lambda t: t.theme.confidence)
    return primary.theme.stage


def _merge_drivers(tagged: list[_TaggedTheme]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tagged:
        for d in t.theme.key_drivers:
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out[:6]


def _merge_risks(tagged: list[_TaggedTheme]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tagged:
        for r in t.theme.risks:
            if r not in seen:
                seen.add(r)
                out.append(r)
    return out[:5]


def _merge_tickers(tagged: list[_TaggedTheme]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tagged:
        for x in t.theme.tickers_or_sectors:
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out[:8]


def _tokens(text: str) -> set[str]:
    return {w for w in text.lower().split() if len(w) > 3}


def _narrative_sourced_for_cluster(
    narrative: NarrativeReport,
    tagged: list[_TaggedTheme],
) -> tuple[list[SourcedItem], list[SourcedItem]]:
    """Attach narrative sourced items only when this cluster includes narrative themes."""
    narrative_in_cluster = [t for t in tagged if t.agent == AGENT_NARRATIVE]
    if not narrative_in_cluster:
        return [], []

    anchor = " ".join(
        f"{t.theme.name} {t.theme.thesis}" for t in narrative_in_cluster
    )
    anchor_tokens = _tokens(anchor)

    drivers: list[SourcedItem] = []
    risks: list[SourcedItem] = []
    for item in narrative.key_drivers_sourced:
        if _tokens(item.text) & anchor_tokens:
            drivers.append(item)
    for item in narrative.risks_sourced:
        if _tokens(item.text) & anchor_tokens:
            risks.append(item)
    return drivers, risks


def assemble(
    regime: RegimeReport,
    narrative: NarrativeReport,
    markets: MarketsReport,
    *,
    as_of: date,
) -> InvestmentBrief:
    tagged_all = _collect_tagged(regime, narrative, markets)
    groups = _cluster_tagged(tagged_all)

    final_themes: list[FinalTheme] = []
    for group in groups:
        agents = sorted({t.agent for t in group})
        primary = max(group, key=lambda t: t.theme.confidence)
        stage = _pick_stage(group)
        avg_conf = sum(t.theme.confidence for t in group) / len(group)
        consensus = min(1.0, len(agents) / 3.0)
        agent_stages = _merge_agent_stages(group)
        drivers_sourced, risks_sourced = _narrative_sourced_for_cluster(narrative, group)

        rationales = [t.theme.stage_rationale for t in group if t.theme.stage_rationale]
        synthesis = " ".join(rationales[:2]) if rationales else primary.theme.thesis
        display_name = _group_display_name(group)

        final_themes.append(
            FinalTheme(
                name=display_name,
                subtitle=primary.theme.subtitle,
                thesis=_merge_theses(group),
                stage=stage,
                stage_label=stage_label(stage),
                consensus_score=consensus,
                investability_score=min(1.0, max(0.0, avg_conf)),
                agent_stages=agent_stages,
                contributing_agents=agents,
                primary_agent=primary.agent,
                synthesis=synthesis[:500],
                key_drivers=_merge_drivers(group),
                risks=_merge_risks(group),
                tickers_or_sectors=_merge_tickers(group),
                key_drivers_sourced=drivers_sourced,
                risks_sourced=risks_sourced,
            )
        )

    final_themes.sort(key=lambda t: t.investability_score, reverse=True)
    final_themes = final_themes[:8]

    top_names = ", ".join(t.name for t in final_themes[:2]) if final_themes else "none"
    executive = (
        f"{regime.regime_backdrop} "
        f"Headline tone: {narrative.narrative_sentiment}. {narrative.narrative_backdrop} "
        f"Top themes: {top_names}."
    ).strip()

    regime_view = (
        f"{regime.regime_backdrop} Dominant regime: {regime.dominant_regime}. "
        + " ".join(regime.cross_asset_signals[:3])
    ).strip()
    narrative_view = narrative.narrative_backdrop
    markets_fundamentals_view = markets.fundamentals_view or (
        f"Market style: {markets.market_style}. " + " ".join(markets.valuation_notes[:3])
    )
    markets_vol_view = markets.vol_view or (
        f"Vol regime: {markets.vol_regime}. " + " ".join(markets.vol_signals[:3])
    )
    markets_themes = list(markets.fundamentals_themes) + list(markets.vol_themes)

    return InvestmentBrief(
        report_date=format_date_iso(as_of),
        as_of_context="",
        executive_summary=executive[:1200],
        regime_view=regime_view[:2000],
        narrative_view=narrative_view[:2000],
        markets_fundamentals_view=markets_fundamentals_view[:2000],
        markets_vol_view=markets_vol_view[:2000],
        narrative_citations=narrative.citations,
        data_sources=[],
        fundamentals_notes=[],
        themes=final_themes,
        regime_themes=regime.themes,
        narrative_themes=narrative.themes,
        markets_themes=markets_themes,
    )
