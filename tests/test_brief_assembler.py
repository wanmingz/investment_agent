"""Unit tests for v2 brief assembler."""

from datetime import date

from investment_agent.brief_assembler import assemble
from investment_agent.models import (
    AgentTheme,
    MarketsReport,
    NarrativeReport,
    RegimeReport,
    SourcedItem,
    ThemeStage,
)


def _theme(name: str, agent_conf: float = 0.8) -> AgentTheme:
    return AgentTheme(
        name=name,
        thesis=f"Thesis for {name}",
        stage=ThemeStage.MID,
        stage_rationale="test",
        confidence=agent_conf,
        key_drivers=["driver"],
        risks=["risk"],
        tickers_or_sectors=["XLK"],
    )


def test_assemble_clusters_and_maps_views():
    regime = RegimeReport(
        macro_backdrop="Macro backdrop.",
        dominant_regime="soft landing",
        themes=[_theme("AI Infrastructure")],
        cross_asset_signals=["rates stable"],
    )
    narrative = NarrativeReport(
        news_backdrop="News backdrop.",
        narrative_sentiment="neutral",
        themes=[_theme("AI Infrastructure", 0.7)],
        key_drivers_sourced=[
            SourcedItem(
                text="Infrastructure spending accelerates",
                citation_ids=["fh-1"],
            )
        ],
        citations=[],
    )
    markets = MarketsReport(
        market_style="growth",
        vol_regime="normal",
        equity_view="Equity paragraph.",
        quant_view="Quant paragraph.",
        equity_themes=[_theme("Software margin recovery")],
        quant_themes=[_theme("Low vol tech carry")],
    )
    brief = assemble(regime, narrative, markets, as_of=date(2026, 6, 16))
    assert brief.macro_view
    assert brief.news_view == "News backdrop."
    assert brief.equity_view == "Equity paragraph."
    assert len(brief.themes) >= 2
    multi = [t for t in brief.themes if len(t.contributing_agents) >= 2]
    assert multi, "expected cluster with macro+news overlap"
    equity_only = next(t for t in brief.themes if t.name == "Software margin recovery")
    assert equity_only.key_drivers_sourced == []
    ai_cluster = next(t for t in brief.themes if "Infrastructure" in t.name)
    assert len(ai_cluster.key_drivers_sourced) >= 1
