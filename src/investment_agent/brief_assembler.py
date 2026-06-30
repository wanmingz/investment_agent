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


def theme_key(name: str) -> str:
    """Stable id for clustering similar theme titles across agents."""
    raw = name.lower().strip()
    key = _THEME_KEY_RE.sub("-", raw).strip("-")
    return key or "theme"


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
    clusters: dict[str, list[_TaggedTheme]] = defaultdict(list)
    for item in tagged_all:
        clusters[theme_key(item.theme.name)].append(item)

    final_themes: list[FinalTheme] = []
    for _key, group in clusters.items():
        agents = sorted({t.agent for t in group})
        primary = max(group, key=lambda t: t.theme.confidence)
        stage = _pick_stage(group)
        avg_conf = sum(t.theme.confidence for t in group) / len(group)
        consensus = min(1.0, len(agents) / 2.0)
        agent_stages = {t.agent: t.theme.stage for t in group}
        drivers_sourced, risks_sourced = _narrative_sourced_for_cluster(narrative, group)

        rationales = [t.theme.stage_rationale for t in group if t.theme.stage_rationale]
        synthesis = " ".join(rationales[:2]) if rationales else primary.theme.thesis

        final_themes.append(
            FinalTheme(
                name=primary.theme.name,
                subtitle=primary.theme.subtitle,
                thesis=primary.theme.thesis,
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
    if len(final_themes) < 4 and tagged_all:
        for item in tagged_all:
            if any(ft.name == item.theme.name for ft in final_themes):
                continue
            final_themes.append(
                FinalTheme(
                    name=item.theme.name,
                    subtitle=item.theme.subtitle,
                    thesis=item.theme.thesis,
                    stage=item.theme.stage,
                    stage_label=stage_label(item.theme.stage),
                    consensus_score=0.5,
                    investability_score=item.theme.confidence,
                    agent_stages={item.agent: item.theme.stage},
                    contributing_agents=[item.agent],
                    primary_agent=item.agent,
                    synthesis=item.theme.stage_rationale or item.theme.thesis,
                    key_drivers=item.theme.key_drivers,
                    risks=item.theme.risks,
                    tickers_or_sectors=item.theme.tickers_or_sectors,
                )
            )
            if len(final_themes) >= 4:
                break
        final_themes.sort(key=lambda t: t.investability_score, reverse=True)

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
