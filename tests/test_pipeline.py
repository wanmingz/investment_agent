"""Unit tests for data plane + brief assembler."""

from datetime import date

from investment_agent.brief_assembler import assemble
from investment_agent.agents.markets.price import PriceMetrics
from investment_agent.agents.markets.snapshot import FundamentalsSnapshot, SymbolFundamentals, VolSnapshot
from investment_agent.agents.markets.valuation import ValuationMetrics
from investment_agent.agents.regime.input import RegimeInput, build_regime_input
from investment_agent.agents.markets.input import MarketSnapshots
from investment_agent.data_plane import build_data_plane
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
from investment_agent.storage import normalize_brief_dict


def _theme(
    name: str,
    agent_conf: float = 0.8,
    *,
    tickers: list[str] | None = None,
) -> AgentTheme:
    return AgentTheme(
        name=name,
        thesis=f"Thesis for {name}",
        stage=ThemeStage.MID,
        stage_rationale="test",
        confidence=agent_conf,
        key_drivers=["driver"],
        risks=["risk"],
        tickers_or_sectors=tickers if tickers is not None else ["XLK"],
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


def test_regime_input_has_context_fields():
    ri = RegimeInput(
        as_of=date(2026, 6, 16),
        region="US",
        regime_context_block="## Cross-asset",
        context_notes=("regime:ok",),
    )
    assert not hasattr(ri, "context_block")
    assert ri.regime_context_block.startswith("##")


def test_build_regime_input_from_market_snapshots():
    fundamentals = FundamentalsSnapshot(
        as_of="2026-06-16",
        rows=[_row("Benchmark", "SPY", 2.0), _row("Tech", "XLK", 5.0, vs_spy=3.0)],
        signals=["Tech: strong 20d momentum (+5.0%)"],
    )
    vol = VolSnapshot(vix_level=18.5, vix_20d_change_pct=4.2, sector_vol={"Tech": 0.22}, notes=[])
    snap = MarketSnapshots(fundamentals=fundamentals, vol=vol)
    regime_input, notes = build_regime_input(snap, as_of=date(2026, 6, 16), region="global")
    assert "VIX proxy" in regime_input.regime_context_block
    assert "XLK" in regime_input.regime_context_block


def test_build_data_plane_wires_three_agent_inputs():
    from unittest.mock import patch

    fundamentals = FundamentalsSnapshot(
        as_of="2026-06-16",
        rows=[_row("Benchmark", "SPY", 2.0)],
        signals=[],
    )
    vol = VolSnapshot(vix_level=20.0, vix_20d_change_pct=1.0, sector_vol={}, notes=[])

    with (
        patch(
            "investment_agent.data_plane.fetch_market_snapshots",
            return_value=(MarketSnapshots(fundamentals, vol), ["market:ok"]),
        ),
        patch(
            "investment_agent.data_plane.build_narrative_input",
            return_value=(
                __import__(
                    "investment_agent.agents.narrative.input",
                    fromlist=["NarrativeInput"],
                ).NarrativeInput(
                    as_of=date(2026, 6, 16),
                    region="global",
                    retrieval_query="q",
                    articles_in_corpus=0,
                    articles_retrieved=0,
                    ingest_notes=[],
                    context_block="",
                ),
                [],
            ),
        ),
    ):
        from investment_agent.config import Settings

        plane = build_data_plane(
            Settings(
                api_key="k",
                base_url="http://x",
                model="m",
                market_region="global",
                provider="openai",
            ),
            as_of=date(2026, 6, 16),
        )
    assert plane.regime_input.regime_context_block
    assert plane.markets_input.fundamentals is fundamentals
    assert plane.narrative_input.retrieval_query == "q"


def test_assemble_fuzzy_clusters_sector_themes():
    regime = RegimeReport(
        regime_backdrop="Regime.",
        dominant_regime="soft landing",
        themes=[_theme("Financials sector outperformance", 0.85, tickers=["XLF"])],
        cross_asset_signals=[],
    )
    narrative = NarrativeReport(
        narrative_backdrop="News.",
        narrative_sentiment="neutral",
        themes=[_theme("Bank earnings momentum", 0.75, tickers=["XLF"])],
        citations=[],
    )
    markets = MarketsReport(
        market_style="value",
        vol_regime="normal",
        fundamentals_themes=[
            _theme("Financials momentum vs SPY", 0.8, tickers=["XLF"]),
        ],
        vol_themes=[],
    )
    brief = assemble(regime, narrative, markets, as_of=date(2026, 6, 16))
    assert len(brief.themes) == 1
    merged = brief.themes[0]
    assert merged.name == "Financials"
    assert len(merged.contributing_agents) >= 2
    assert AGENT_REGIME in merged.agent_stages
    assert AGENT_NARRATIVE in merged.agent_stages
    assert AGENT_MARKETS in merged.agent_stages


def test_assemble_merges_markets_fundamentals_and_vol_same_sector():
    markets = MarketsReport(
        market_style="value",
        vol_regime="normal",
        fundamentals_themes=[_theme("Financials earnings strength", 0.9, tickers=["XLF"])],
        vol_themes=[_theme("Low vol in banks", 0.7, tickers=["XLF"])],
    )
    brief = assemble(
        RegimeReport(regime_backdrop="r", dominant_regime="soft", themes=[]),
        NarrativeReport(narrative_backdrop="n", narrative_sentiment="neutral", themes=[], citations=[]),
        markets,
        as_of=date(2026, 6, 16),
    )
    assert len(brief.themes) == 1
    assert brief.themes[0].name == "Financials"
    assert brief.themes[0].contributing_agents == [AGENT_MARKETS]


def test_assemble_clusters_and_maps_views():
    regime = RegimeReport(
        regime_backdrop="Regime backdrop.",
        dominant_regime="soft landing",
        themes=[_theme("AI Infrastructure", tickers=["AIQ"])],
        cross_asset_signals=["rates stable"],
    )
    narrative = NarrativeReport(
        narrative_backdrop="Narrative backdrop.",
        narrative_sentiment="neutral",
        themes=[_theme("AI Infrastructure", 0.7, tickers=["AIQ"])],
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
        fundamentals_themes=[_theme("AI Infrastructure buildout", tickers=["AIQ"])],
        vol_themes=[_theme("AI vol regime", tickers=["AIQ"])],
    )
    brief = assemble(regime, narrative, markets, as_of=date(2026, 6, 16))
    assert brief.regime_view
    assert brief.narrative_view == "Narrative backdrop."
    assert brief.markets_fundamentals_view == "Fundamentals paragraph."
    assert len(brief.themes) == 1
    ai_theme = brief.themes[0]
    assert ai_theme.name == "AI"
    assert len(ai_theme.contributing_agents) == 3
    assert AGENT_REGIME in ai_theme.contributing_agents
    assert AGENT_NARRATIVE in ai_theme.contributing_agents
    assert AGENT_MARKETS in ai_theme.contributing_agents
    assert len(ai_theme.key_drivers_sourced) >= 1


def test_format_context_block_truncates_for_token_budget():
    from investment_agent.agents.narrative.ingest import NewsArticle
    from investment_agent.agents.narrative.rag import format_context_block

    articles = [
        NewsArticle(
            id=f"n-{i}",
            title=f"Headline {i}",
            summary="word " * 400,
            url="https://example.com",
            source="test",
        )
        for i in range(12)
    ]
    block = format_context_block(articles, max_summary_chars=100, max_total_chars=1500)
    assert len(block) < 2500
    assert "omitted" in block or block.count("[n-") < 12


def test_combined_theme_score_sort_order():
    from investment_agent.models import FinalTheme, ThemeStage

    def rank(t: FinalTheme) -> float:
        return t.investability_score + t.consensus_score

    low = FinalTheme(
        name="A",
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=0.33,
        investability_score=0.9,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=[],
    )
    high = FinalTheme(
        name="B",
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=1.0,
        investability_score=0.7,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=[],
    )
    assert rank(high) > rank(low)
    ranked = sorted([low, high], key=rank, reverse=True)
    assert ranked[0].name == "B"


def test_normalize_brief_dict_fills_theme_defaults():
    data = normalize_brief_dict(
        {
            "as_of_context": "As of 2026-01-01",
            "executive_summary": "x",
            "regime_view": "r",
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
                }
            ],
        }
    )
    theme = data["themes"][0]
    assert theme["contributing_agents"] == []
    assert theme["agent_stages"] == {}
    assert data["regime_themes"] == []
