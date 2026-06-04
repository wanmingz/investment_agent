import json
from collections import defaultdict
from datetime import date

from investment_agent.agents import EquityResearchAnalyst, MacroEconomist, QuantAnalyst
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
    QuantReport,
    ThemeStage,
    stage_label,
)

SYNTHESIS_SYSTEM = """You are the Chief Investment Officer synthesizing three specialist agents.

Agents:
1. Macro Economist — macro regime and policy-driven themes
2. Equity Research Analyst — fundamentals, valuations, earnings
3. Quant Analyst — volatility regime and risk-adjusted timing

Write ALL narrative fields in English only.

Produce a unified investment brief in JSON:
{
  "report_date": "YYYY-MM-DD (must match the analysis date provided in the prompt)",
  "as_of_context": "brief market context note (date will be prefixed automatically)",
  "executive_summary": "3-5 sentences, actionable overview in English",
  "macro_view": "1 paragraph English summary of macro agent",
  "equity_view": "1 paragraph English summary of equity agent",
  "quant_view": "1 paragraph English summary of quant agent",
  "themes": [
    {
      "name": "English theme name",
      "subtitle": "optional short label",
      "thesis": "combined thesis in English",
      "stage": "early"|"early_mid"|"mid"|"mid_late"|"late",
      "stage_label": "Early|Early-Mid|Mid|Mid-Late|Late",
      "consensus_score": 0-1,
      "investability_score": 0-1,
      "agent_stages": {"macro": "early_mid", "equity": "mid", "quant": "early"},
      "synthesis": "why final stage, 2-3 sentences English",
      "key_drivers": [],
      "risks": [],
      "tickers_or_sectors": []
    }
  ]
}

Rules:
- Include 4-6 themes ranked by investability_score descending
- Final stage = weighted judgment; if agents disagree, explain in synthesis and lower consensus_score
- early = positioning, early_mid = validation/diffusion, mid = expansion/monetization,
  mid_late = mature/crowded/vol rising, late = overheated/exit watch
- Use all five stages; prefer early_mid and mid_late when theme is between two pure stages
- Be direct about what to invest NOW vs watch"""


class ThemeOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._macro = MacroEconomist(self._llm, self._settings)
        self._equity = EquityResearchAnalyst(self._llm, self._settings)
        self._quant = QuantAnalyst(self._llm, self._settings)

    def run(self) -> InvestmentBrief:
        as_of = analysis_date()
        vol = fetch_vol_snapshot()

        macro = self._macro.analyze(as_of=as_of)
        equity = self._equity.analyze(macro, as_of=as_of)
        quant = self._quant.analyze(macro, equity, vol, as_of=as_of)

        brief = self._synthesize(macro, equity, quant, as_of=as_of)
        return self._enrich_brief(brief, as_of=as_of)

    def _synthesize(
        self,
        macro: MacroReport,
        equity: EquityReport,
        quant: QuantReport,
        *,
        as_of: date,
    ) -> InvestmentBrief:
        payload = {
            "macro_report": macro.model_dump(),
            "equity_report": equity.model_dump(),
            "quant_report": quant.model_dump(),
        }
        user = f"""Synthesize the three agent reports into a unified CIO brief.

Analysis date (today): {format_date_display(as_of)} ({format_date_iso(as_of)})
Set report_date to "{format_date_iso(as_of)}" exactly.
Respond in English only.

Reports:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Return ranked themes with final stage and per-agent stage breakdown."""
        return self._llm.structured(
            system=SYNTHESIS_SYSTEM, user=user, schema=InvestmentBrief, temperature=0.2
        )

    def _enrich_brief(self, brief: InvestmentBrief, *, as_of: date) -> InvestmentBrief:
        """Set report date, as_of_context prefix, and stage labels."""
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
        return brief.model_copy(
            update={
                "report_date": iso,
                "as_of_context": build_as_of_context(
                    brief.as_of_context,
                    as_of=as_of,
                    region=self._settings.market_region,
                ),
                "themes": themes,
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
