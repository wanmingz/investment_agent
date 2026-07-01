from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from investment_agent.agents import MarketsAgent, NarrativeAgent, RegimeAgent
from investment_agent.brief_assembler import assemble
from investment_agent.config import Settings
from investment_agent.data_plane import DataPlaneSnapshot, build_data_plane
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

        if regime is None or narrative is None or markets is None:
            regime, narrative, markets = self._run_pending_agents(
                plane=plane,
                regime=regime,
                narrative=narrative,
                markets=markets,
                use_resume=use_resume,
            )

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

    def _run_pending_agents(
        self,
        *,
        plane: DataPlaneSnapshot,
        regime: RegimeReport | None,
        narrative: NarrativeReport | None,
        markets: MarketsReport | None,
        use_resume: bool,
    ) -> tuple[RegimeReport | None, NarrativeReport | None, MarketsReport | None]:
        tasks: list[tuple[str, object]] = []
        if regime is None:
            tasks.append(("regime", plane.regime_input))
        if narrative is None:
            tasks.append(("narrative", plane.narrative_input))
        if markets is None:
            tasks.append(("markets", plane.markets_input))

        delay = self._settings.llm_agent_delay_seconds

        def _save(key: str, result: object) -> None:
            nonlocal regime, narrative, markets
            if key == "regime":
                regime = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_regime(regime)  # type: ignore[arg-type]
            elif key == "narrative":
                narrative = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_narrative(narrative)  # type: ignore[arg-type]
            else:
                markets = result  # type: ignore[assignment]
                if use_resume:
                    checkpoint.save_markets(markets)  # type: ignore[arg-type]

        def _analyze(key: str, agent_input: object) -> object:
            if key == "regime":
                return self._regime.analyze(agent_input)  # type: ignore[arg-type]
            if key == "narrative":
                return self._narrative.analyze(agent_input)  # type: ignore[arg-type]
            return self._markets.analyze(agent_input)  # type: ignore[arg-type]

        if self._settings.llm_parallel_agents and len(tasks) > 1:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(_analyze, key, agent_input): key for key, agent_input in tasks
                }
                for fut in as_completed(futures):
                    key = futures[fut]
                    _save(key, fut.result())
            return regime, narrative, markets

        for i, (key, agent_input) in enumerate(tasks):
            if i > 0 and delay > 0:
                time.sleep(delay)
            _save(key, _analyze(key, agent_input))
        return regime, narrative, markets

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
            "Regime context — derived cross-asset block (yfinance vol + sector ETF snapshot)",
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
                "narrative_view": brief.narrative_view or narrative.narrative_backdrop,
                "narrative_citations": narrative.citations,
                "data_sources": sources,
                "fundamentals_notes": fund_notes,
                "regime_themes": regime.themes,
                "narrative_themes": narrative.themes,
                "markets_themes": list(markets.fundamentals_themes)
                + list(markets.vol_themes),
            }
        )


def compute_stage_consensus(
    regime_themes: list[AgentTheme],
    narrative_themes: list[AgentTheme],
    markets_themes: list[AgentTheme],
) -> dict[str, dict[str, ThemeStage]]:
    """Map theme_key -> agent stages (regime / narrative / markets)."""
    from collections import defaultdict

    from investment_agent.brief_assembler import theme_key
    from investment_agent.models import AGENT_MARKETS, AGENT_NARRATIVE, AGENT_REGIME

    by_agent = {
        AGENT_REGIME: regime_themes,
        AGENT_NARRATIVE: narrative_themes,
        AGENT_MARKETS: markets_themes,
    }
    merged: dict[str, dict[str, ThemeStage]] = defaultdict(dict)
    for agent, themes in by_agent.items():
        for th in themes:
            merged[theme_key(th.name)][agent] = th.stage
    return dict(merged)
