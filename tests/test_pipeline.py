"""Unit tests for data plane + brief assembler."""

from datetime import date

from investment_agent.brief_assembler import assemble
from investment_agent.data.price import PriceMetrics
from investment_agent.data.snapshot import FundamentalsSnapshot, SymbolFundamentals
from investment_agent.data.valuation import ValuationMetrics
from investment_agent.data_plane import RegimeInput, build_data_plane
from investment_agent.data.snapshot import VolSnapshot
from investment_agent.models import (
    AGENT_MARKETS,
    AGENT_NARRATIVE,
    AGENT_REGIME,
    AgentTheme,
    MarketsReport,
    NarrativeReport,
    RegimeReport,
    SourcedItem,
    ThemeStage,
)
from investment_agent.storage import migrate_brief_dict


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


def _row(label: str, symbol: str, ret_20d: float, vs_spy: float | None = None) -> SymbolFundamentals:
    return SymbolFundamentals(
        label=label,
        symbol=symbol,
        price=PriceMetrics(
            symbol=symbol,
            label=label,
            last_close=100.0,
            return_20d_pct=ret_20d,
            vs_spy_20d_pct=vs_spy,
        ),
        valuation=ValuationMetrics(symbol=symbol, label=label, forward_pe=20.0),
    )


def test_regime_input_has_macro_context_fields():
    ri = RegimeInput(
        as_of=date(2026, 6, 16),
        region="US",
        macro_context_block="## Cross-asset",
        context_notes=("regime:ok",),
    )
    assert not hasattr(ri, "context_block")
    assert ri.macro_context_block.startswith("##")


def test_build_data_plane_regime_context_from_snapshots():
    """Regime slice gets macro_context_block when plane is built (integration smoke)."""
    from unittest.mock import patch

    fundamentals = FundamentalsSnapshot(
        as_of="2026-06-16",
        rows=[_row("Benchmark", "SPY", 2.0), _row("Tech", "XLK", 5.0, vs_spy=3.0)],
        signals=["Tech: strong 20d momentum (+5.0%)"],
    )
    vol = VolSnapshot(vix_level=18.5, vix_20d_change_pct=4.2, sector_vol={"Tech": 0.22}, notes=[])

    with (
        patch("investment_agent.data_plane.fetch_news_articles", return_value=([], [])),
        patch("investment_agent.data_plane.retrieve_articles", return_value=[]),
        patch("investment_agent.data_plane.format_context_block", return_value=""),
        patch("investment_agent.data_plane.fetch_fundamentals_snapshot", return_value=fundamentals),
        patch("investment_agent.data_plane.fetch_vol_snapshot", return_value=vol),
    ):
        from investment_agent.config import Settings

        plane = build_data_plane(
            Settings(
                api_key="k",
                base_url="http://x",
                model="m",
                market_region="global",
                provider="openai",
            )
        )
    block = plane.regime_input.macro_context_block
    assert "VIX proxy" in block
    assert "XLK" in block


def test_assemble_clusters_and_maps_views():
    regime = RegimeReport(
        regime_backdrop="Regime backdrop.",
        dominant_regime="soft landing",
        themes=[_theme("AI Infrastructure")],
        cross_asset_signals=["rates stable"],
    )
    narrative = NarrativeReport(
        narrative_backdrop="Narrative backdrop.",
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
        fundamentals_view="Fundamentals paragraph.",
        vol_view="Vol paragraph.",
        fundamentals_themes=[_theme("Software margin recovery")],
        vol_themes=[_theme("Low vol tech carry")],
    )
    brief = assemble(regime, narrative, markets, as_of=date(2026, 6, 16))
    assert brief.regime_view
    assert brief.narrative_view == "Narrative backdrop."
    assert brief.markets_fundamentals_view == "Fundamentals paragraph."
    assert len(brief.themes) >= 2
    multi = [t for t in brief.themes if len(t.contributing_agents) >= 2]
    assert multi
    markets_only = next(t for t in brief.themes if t.name == "Software margin recovery")
    assert markets_only.key_drivers_sourced == []
    assert markets_only.contributing_agents == [AGENT_MARKETS]
    ai_cluster = next(t for t in brief.themes if "Infrastructure" in t.name)
    assert len(ai_cluster.key_drivers_sourced) >= 1
    assert AGENT_REGIME in ai_cluster.contributing_agents
    assert AGENT_NARRATIVE in ai_cluster.contributing_agents


def test_migrate_brief_dict_maps_legacy_agent_keys():
    data = migrate_brief_dict(
        {
            "macro_view": "m",
            "news_view": "n",
            "equity_view": "e",
            "quant_view": "q",
            "macro_themes": [],
            "news_themes": [],
            "equity_themes": [{"name": "x"}],
            "quant_themes": [{"name": "y"}],
            "themes": [
                {
                    "name": "T",
                    "thesis": "t",
                    "stage": "mid",
                    "consensus_score": 0.5,
                    "investability_score": 0.5,
                    "synthesis": "s",
                    "key_drivers": [],
                    "risks": [],
                    "tickers_or_sectors": [],
                    "contributing_agents": ["macro", "news", "equity"],
                    "primary_agent": "news",
                    "agent_stages": {"macro": "early", "equity": "mid"},
                }
            ],
            "as_of_context": "As of 2026-01-01",
            "executive_summary": "x",
        }
    )
    assert data["regime_view"] == "m"
    assert data["narrative_view"] == "n"
    assert data["markets_fundamentals_view"] == "e"
    assert data["markets_vol_view"] == "q"
    assert len(data["markets_themes"]) == 2
    theme = data["themes"][0]
    assert theme["contributing_agents"] == [AGENT_MARKETS, AGENT_NARRATIVE, AGENT_REGIME]
    assert theme["primary_agent"] == AGENT_NARRATIVE
    assert theme["agent_stages"] == {AGENT_REGIME: "early", AGENT_MARKETS: "mid"}
