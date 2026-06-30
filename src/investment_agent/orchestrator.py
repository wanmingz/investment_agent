from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from investment_agent.agents import MarketsAgent, NarrativeAgent, RegimeAgent
from investment_agent.brief_assembler import assemble
from investment_agent.config import Settings
from investment_agent.data_plane import build_data_plane
from investment_agent.inputs import DataPlaneSnapshot
from investment_agent.dates import analysis_date, build_as_of_context, format_date_iso
from investment_agent import checkpoint
from investment_agent.llm import LLMClient
from investment_agent.models import (
    AgentTheme,
    InvestmentBrief,
    MarketsReport,
    NarrativeReport,
    RegimeReport,
    ThemeStage,
    stage_label,
)

class ThemeOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._regime = RegimeAgent(self._llm)
        self._narrative = NarrativeAgent(self._llm)
        self._markets = MarketsAgent(self._llm)

    def run(self, *, resume: bool | None = None) -> InvestmentBrief:
        as_of = analysis_date()
        region = self._settings.market_region
        use_resume = resume if resume is not None else checkpoint.is_resume_enabled()

        if use_resume and not checkpoint.meta_matches(as_of=as_of, region=region):
            checkpoint.clear_checkpoint()
        if use_resume:
            checkpoint.save_run_meta(as_of=as_of, region=region)

        plane = checkpoint.load_data_plane() if use_resume else None
        if plane is None:
            plane = build_data_plane(self._settings, as_of=as_of)
            if use_resume:
                checkpoint.save_data_plane(plane)

        regime = checkpoint.load_regime() if use_resume else None
        narrative = checkpoint.load_narrative() if use_resume else None
        markets = checkpoint.load_markets() if use_resume else None

        pending: dict[str, object] = {}
        if regime is None:
            pending["regime"] = self._regime
        if narrative is None:
            pending["narrative"] = self._narrative
        if markets is None:
            pending["markets"] = self._markets

        if pending:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {}
                if regime is None:
                    futures[pool.submit(self._regime.analyze, plane.regime_input)] = "regime"
                if narrative is None:
                    futures[pool.submit(self._narrative.analyze, plane.narrative_input)] = "narrative"
                if markets is None:
                    futures[pool.submit(self._markets.analyze, plane.markets_input)] = "markets"
                for fut in as_completed(futures):
                    key = futures[fut]
                    result = fut.result()
                    if key == "regime":
                        regime = result
                        if use_resume:
                            checkpoint.save_regime(regime)
                    elif key == "narrative":
                        narrative = result
                        if use_resume:
                            checkpoint.save_narrative(narrative)
                    else:
                        markets = result
                        if use_resume:
                            checkpoint.save_markets(markets)

        assert regime is not None and narrative is not None and markets is not None
        brief = assemble(regime, narrative, markets, as_of=as_of)
        brief = self._enrich_brief(
            brief,
            regime=regime,
            narrative=narrative,
            markets=markets,
            plane=plane,
            as_of=as_of,
        )
        if use_resume:
            checkpoint.clear_checkpoint()
        return brief

    def _enrich_brief(
        self,
        brief: InvestmentBrief,
        *,
        regime: RegimeReport,
        narrative: NarrativeReport,
        markets: MarketsReport,
        plane: DataPlaneSnapshot,
        as_of: date,
    ) -> InvestmentBrief:
        iso = format_date_iso(as_of)
        themes = []
        for t in brief.themes:
            stage = t.stage if isinstance(t.stage, ThemeStage) else ThemeStage(t.stage)
            themes.append(
                t.model_copy(
                    update={
                        "stage": stage,
                        "stage_label": t.stage_label or stage_label(stage),
                    }
                )
            )

        sources = [
            f"LLM ({self._settings.provider}/{self._settings.model}) — regime, narrative, markets (v2)",
            "Programmatic BriefAssembler — theme clustering (no CIO LLM)",
            "Data Plane — Finnhub/TickerTick news, yfinance fundamentals & vol",
        ]
        if self._settings.finnhub_api_key:
            sources.append("Finnhub market news API")
        sources.append("TickerTick curated feed (free)")
        sources.append("yfinance — sector ETF fundamentals and volatility")
        if plane.data_plane_notes:
            sources.append("Data plane: " + "; ".join(plane.data_plane_notes[:4]))

        fund_notes = plane.markets_input.fundamentals.summary_lines()

        return brief.model_copy(
            update={
                "report_date": iso,
                "as_of_context": build_as_of_context(
                    brief.as_of_context,
                    as_of=as_of,
                    region=self._settings.market_region,
                ),
                "themes": themes,
                "news_view": brief.news_view or narrative.news_backdrop,
                "news_citations": narrative.citations,
                "data_sources": sources,
                "fundamentals_notes": fund_notes,
                "macro_themes": regime.themes,
                "news_themes": narrative.themes,
                "equity_themes": markets.equity_themes,
                "quant_themes": markets.quant_themes,
            }
        )


def compute_stage_consensus(
    macro_themes: list[AgentTheme],
    news_themes: list[AgentTheme],
    equity_themes: list[AgentTheme],
    quant_themes: list[AgentTheme],
) -> dict[str, dict[str, ThemeStage]]:
    """Map theme_key -> agent stages (macro/news/equity/quant labels for brief compat)."""
    from collections import defaultdict

    from investment_agent.themes import theme_key

    by_agent = {
        "macro": macro_themes,
        "news": news_themes,
        "equity": equity_themes,
        "quant": quant_themes,
    }
    merged: dict[str, dict[str, ThemeStage]] = defaultdict(dict)
    for agent, themes in by_agent.items():
        for th in themes:
            merged[theme_key(th.name)][agent] = th.stage
    return dict(merged)
