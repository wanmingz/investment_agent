import json
from collections import defaultdict
from datetime import date

from investment_agent.agents import (
    EquityResearchAnalyst,
    MacroEconomist,
    NewsAnalyst,
    QuantAnalyst,
)
from investment_agent.config import Settings
from investment_agent.dates import (
    analysis_date,
    build_as_of_context,
    format_date_display,
    format_date_iso,
)
from investment_agent import checkpoint
from investment_agent.llm import LLMClient
from investment_agent.data import fetch_fundamentals_snapshot
from investment_agent.data.snapshot import FundamentalsSnapshot
from investment_agent.market_data import fetch_vol_snapshot
from investment_agent.models import (
    AgentTheme,
    EquityReport,
    FinalTheme,
    InvestmentBrief,
    MacroReport,
    NewsReport,
    QuantReport,
    ThemeStage,
    stage_label,
)

SYNTHESIS_SYSTEM = """You are the Chief Investment Officer synthesizing four specialist agents.

Each agent produced its OWN theme list (names may differ). Your job is to MERGE and RANK, not force identical names.

Agents:
1. Macro Economist — macro regime themes
2. News Analyst (RAG) — headline-driven themes (may differ from macro)
3. Equity Research Analyst — fundamentals-driven themes
4. Quant Analyst — volatility/risk themes

Write ALL narrative fields in English only.

Produce a unified investment brief in JSON:
{
  "report_date": "YYYY-MM-DD",
  "as_of_context": "brief market context",
  "executive_summary": "3-5 sentences",
  "macro_view": "1 paragraph",
  "news_view": "1 paragraph",
  "equity_view": "1 paragraph",
  "quant_view": "1 paragraph",
  "data_sources": ["strings"],
  "themes": [
    {
      "name": "final theme name (may synthesize similar concepts)",
      "subtitle": "optional",
      "thesis": "combined thesis",
      "stage": "early"|"early_mid"|"mid"|"mid_late"|"late",
      "stage_label": "Early|...",
      "consensus_score": 0-1,
      "investability_score": 0-1,
      "contributing_agents": ["macro", "news"],
      "primary_agent": "news",
      "agent_stages": {"macro": "early_mid", "news": "mid"},
      "synthesis": "2-3 sentences",
      "key_drivers": [],
      "risks": [],
      "key_drivers_sourced": [{"text": "...", "citation_ids": ["id"]}],
      "risks_sourced": [],
      "tickers_or_sectors": []
    }
  ]
}

Merge rules:
- Include 4-8 final themes ranked by investability_score descending
- Cluster similar concepts (e.g. "AI capex" and "Hyperscaler spend") into one final theme when appropriate
- contributing_agents: list every agent that had a related theme in their own list
- primary_agent: agent that best originated the final thesis
- agent_stages: ONLY include agents that actually proposed this cluster; omit agents with no related theme
- consensus_score: high if 2+ agents covered similar idea; low if only one agent
- Prefer news citation_ids for key_drivers_sourced when supported by news report
- Final stage = weighted judgment using only agent_stages that exist; note disagreement in synthesis
- Do not copy macro theme names onto unrelated news-only themes"""


class ThemeOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._macro = MacroEconomist(self._llm, self._settings)
        self._news = NewsAnalyst(self._llm, self._settings)
        self._equity = EquityResearchAnalyst(self._llm, self._settings)
        self._quant = QuantAnalyst(self._llm, self._settings)

    def run(self, *, resume: bool | None = None) -> InvestmentBrief:
        as_of = analysis_date()
        region = self._settings.market_region
        use_resume = resume if resume is not None else checkpoint.is_resume_enabled()
        vol = fetch_vol_snapshot()

        if use_resume and not checkpoint.meta_matches(as_of=as_of, region=region):
            checkpoint.clear_checkpoint()
        if use_resume:
            checkpoint.save_run_meta(as_of=as_of, region=region)

        macro = checkpoint.load_macro() if use_resume else None
        if macro is None:
            macro = self._macro.analyze(as_of=as_of)
            if use_resume:
                checkpoint.save_macro(macro)

        news = checkpoint.load_news() if use_resume else None
        if news is None:
            news = self._news.analyze(as_of=as_of)
            if use_resume:
                checkpoint.save_news(news)

        fundamentals = checkpoint.load_fundamentals() if use_resume else None
        if fundamentals is None:
            fundamentals = fetch_fundamentals_snapshot(
                [],
                as_of=as_of,
                finnhub_key=self._settings.finnhub_api_key,
            )
            if use_resume:
                checkpoint.save_fundamentals(fundamentals)

        equity = checkpoint.load_equity() if use_resume else None
        if equity is None:
            equity = self._equity.analyze(
                news, fundamentals=fundamentals, as_of=as_of
            )
            if use_resume:
                checkpoint.save_equity(equity)

        quant = checkpoint.load_quant() if use_resume else None
        if quant is None:
            quant = self._quant.analyze(
                vol,
                dominant_regime=macro.dominant_regime,
                as_of=as_of,
            )
            if use_resume:
                checkpoint.save_quant(quant)

        brief = self._synthesize(
            macro, news, equity, quant, fundamentals=fundamentals, as_of=as_of
        )
        brief = self._enrich_brief(
            brief,
            news=news,
            macro=macro,
            equity=equity,
            quant=quant,
            fundamentals=fundamentals,
            as_of=as_of,
        )
        if use_resume:
            checkpoint.clear_checkpoint()
        return brief

    def _synthesize(
        self,
        macro: MacroReport,
        news: NewsReport,
        equity: EquityReport,
        quant: QuantReport,
        fundamentals: FundamentalsSnapshot | None = None,
        *,
        as_of: date,
    ) -> InvestmentBrief:
        payload = {
            "macro_report": macro.model_dump(),
            "news_report": news.model_dump(),
            "equity_report": equity.model_dump(),
            "quant_report": quant.model_dump(),
        }
        if fundamentals:
            payload["structured_fundamentals_summary"] = fundamentals.summary_lines()
        user = f"""Synthesize the four agent reports into a unified CIO brief.

Analysis date (today): {format_date_display(as_of)} ({format_date_iso(as_of)})
Set report_date to "{format_date_iso(as_of)}" exactly.
Respond in English only.

Each agent_report has its own "themes" array — names WILL differ. Merge by concept; preserve diversity in final list.
News report includes citations — use citation_ids in key_drivers_sourced when supported.
Equity had yfinance fundamentals — prefer equity_view when citing P/E or returns.

Agent reports:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Return ranked final themes with contributing_agents, primary_agent, and sparse agent_stages (only agents that proposed related themes)."""
        return self._llm.structured(
            system=SYNTHESIS_SYSTEM, user=user, schema=InvestmentBrief, temperature=0.2
        )

    def _enrich_brief(
        self,
        brief: InvestmentBrief,
        *,
        news: NewsReport,
        macro: MacroReport,
        equity: EquityReport,
        quant: QuantReport,
        fundamentals: FundamentalsSnapshot | None = None,
        as_of: date,
    ) -> InvestmentBrief:
        """Set report date, as_of_context prefix, stage labels, and data_sources."""
        iso = format_date_iso(as_of)
        themes: list[FinalTheme] = []
        for t in brief.themes:
            stage = t.stage if isinstance(t.stage, ThemeStage) else ThemeStage(t.stage)
            label = t.stage_label or stage_label(stage)
            themes.append(
                t.model_copy(
                    update={
                        "stage": stage,
                        "stage_label": label,
                    }
                )
            )

        sources = list(brief.data_sources) if brief.data_sources else []
        if not sources:
            sources = [
                f"LLM ({self._settings.provider}/{self._settings.model}) — macro, news, equity, quant, CIO",
                "News RAG — independent headline themes (lexical retrieval)",
                "Independent theme lists per agent — merged at CIO",
            ]
            if self._settings.finnhub_api_key:
                sources.append("Finnhub market news API")
            sources.append("TickerTick curated feed (free)")
            sources.append("yfinance — VIX and sector ETF volatility (quant agent)")
            sources.append(
                "yfinance — sector ETF prices, valuations (equity agent structured block)"
            )
            if self._settings.finnhub_api_key:
                sources.append(
                    "Finnhub recommendation trends — revision proxy for theme tickers"
                )

        fund_notes = list(brief.fundamentals_notes) if brief.fundamentals_notes else []
        if fundamentals and not fund_notes:
            fund_notes = fundamentals.summary_lines()

        news_view = brief.news_view or news.news_backdrop

        return brief.model_copy(
            update={
                "report_date": iso,
                "as_of_context": build_as_of_context(
                    brief.as_of_context,
                    as_of=as_of,
                    region=self._settings.market_region,
                ),
                "themes": themes,
                "news_view": news_view,
                "news_citations": news.citations,
                "data_sources": sources,
                "fundamentals_notes": fund_notes,
                "macro_themes": macro.themes,
                "news_themes": news.themes,
                "equity_themes": equity.themes,
                "quant_themes": quant.themes,
            }
        )


def compute_stage_consensus(
    macro_themes: list[AgentTheme],
    news_themes: list[AgentTheme],
    equity_themes: list[AgentTheme],
    quant_themes: list[AgentTheme],
) -> dict[str, dict[str, ThemeStage]]:
    """Helper for debugging: map theme_key -> agent stages."""
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
