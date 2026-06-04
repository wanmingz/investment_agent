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
from investment_agent.llm import LLMClient
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

Agents:
1. Macro Economist — macro regime and policy-driven themes
2. News Analyst (RAG) — retrieved headlines with citation IDs; use for news-backed drivers/risks
3. Equity Research Analyst — fundamentals, valuations, earnings
4. Quant Analyst — volatility regime and risk-adjusted timing

Write ALL narrative fields in English only.

Produce a unified investment brief in JSON:
{
  "report_date": "YYYY-MM-DD (must match the analysis date provided in the prompt)",
  "as_of_context": "brief market context note (date will be prefixed automatically)",
  "executive_summary": "3-5 sentences, actionable overview in English",
  "macro_view": "1 paragraph English summary of macro agent",
  "news_view": "1 paragraph English summary of news/RAG agent — mention headline tone",
  "equity_view": "1 paragraph English summary of equity agent",
  "quant_view": "1 paragraph English summary of quant agent",
  "data_sources": ["short strings describing data sources used"],
  "themes": [
    {
      "name": "English theme name",
      "subtitle": "optional short label",
      "thesis": "combined thesis in English",
      "stage": "early"|"early_mid"|"mid"|"mid_late"|"late",
      "stage_label": "Early|Early-Mid|Mid|Mid-Late|Late",
      "consensus_score": 0-1,
      "investability_score": 0-1,
      "agent_stages": {"macro": "early_mid", "equity": "mid", "quant": "early", "news": "mid"},
      "synthesis": "why final stage, 2-3 sentences English",
      "key_drivers": [],
      "risks": [],
      "key_drivers_sourced": [{"text": "...", "citation_ids": ["news-id"]}],
      "risks_sourced": [{"text": "...", "citation_ids": ["news-id"]}],
      "tickers_or_sectors": []
    }
  ]
}

Rules:
- Include 4-6 themes ranked by investability_score descending
- Prefer news agent citation_ids for key_drivers_sourced / risks_sourced when supported by news report
- Also include macro/equity/quant drivers in key_drivers (plain strings) when not news-backed
- Final stage = weighted judgment across four agents; lower consensus_score if agents disagree
- Use all five stages; prefer early_mid and mid_late when theme is between two pure stages
- Be direct about what to invest NOW vs watch"""


class ThemeOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._macro = MacroEconomist(self._llm, self._settings)
        self._news = NewsAnalyst(self._llm, self._settings)
        self._equity = EquityResearchAnalyst(self._llm, self._settings)
        self._quant = QuantAnalyst(self._llm, self._settings)

    def run(self) -> InvestmentBrief:
        as_of = analysis_date()
        vol = fetch_vol_snapshot()

        macro = self._macro.analyze(as_of=as_of)
        news = self._news.analyze(macro, as_of=as_of)
        equity = self._equity.analyze(macro, news, as_of=as_of)
        quant = self._quant.analyze(macro, equity, vol, as_of=as_of)

        brief = self._synthesize(macro, news, equity, quant, as_of=as_of)
        return self._enrich_brief(brief, news=news, as_of=as_of)

    def _synthesize(
        self,
        macro: MacroReport,
        news: NewsReport,
        equity: EquityReport,
        quant: QuantReport,
        *,
        as_of: date,
    ) -> InvestmentBrief:
        payload = {
            "macro_report": macro.model_dump(),
            "news_report": news.model_dump(),
            "equity_report": equity.model_dump(),
            "quant_report": quant.model_dump(),
        }
        user = f"""Synthesize the four agent reports into a unified CIO brief.

Analysis date (today): {format_date_display(as_of)} ({format_date_iso(as_of)})
Set report_date to "{format_date_iso(as_of)}" exactly.
Respond in English only.

News report includes citations with ids — use them in key_drivers_sourced / risks_sourced on themes.

Reports:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Return ranked themes with final stage and per-agent stage breakdown (macro, news, equity, quant)."""
        return self._llm.structured(
            system=SYNTHESIS_SYSTEM, user=user, schema=InvestmentBrief, temperature=0.2
        )

    def _enrich_brief(
        self, brief: InvestmentBrief, *, news: NewsReport, as_of: date
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
                f"LLM ({self._settings.provider}/{self._settings.model}) — macro, equity, quant, CIO",
                "News RAG — lexical retrieval over ingested headlines",
            ]
            if self._settings.finnhub_api_key:
                sources.append("Finnhub market news API")
            sources.append("TickerTick curated feed (free)")
            sources.append("yfinance — VIX and sector ETF volatility (quant agent)")

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
            }
        )


def _normalize_name(name: str) -> str:
    return name.lower().strip().replace(" ", "")


def compute_stage_consensus(
    macro_themes: list[AgentTheme],
    equity_themes: list[AgentTheme],
    quant_themes: list[AgentTheme],
) -> dict[str, dict[str, ThemeStage]]:
    """Helper for debugging: map theme name -> agent stages."""
    by_agent = {
        "macro": macro_themes,
        "equity": equity_themes,
        "quant": quant_themes,
    }
    merged: dict[str, dict[str, ThemeStage]] = defaultdict(dict)
    for agent, themes in by_agent.items():
        for th in themes:
            key = _normalize_name(th.name)
            merged[key][agent] = th.stage
    return dict(merged)
