import json
from collections import defaultdict

from investment_agent.agents import EquityResearchAnalyst, MacroEconomist, QuantAnalyst
from investment_agent.config import Settings
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
)

STAGE_ZH = {
    ThemeStage.EARLY: "早期",
    ThemeStage.MID: "中期",
    ThemeStage.LATE: "晚期",
}

SYNTHESIS_SYSTEM = """You are the Chief Investment Officer synthesizing three specialist agents.

Agents:
1. Macro Economist — macro regime and policy-driven themes
2. Equity Research Analyst — fundamentals, valuations, earnings
3. Quant Analyst — volatility regime and risk-adjusted timing

Produce a unified investment brief in JSON:
{
  "as_of_context": "brief date/market context note",
  "executive_summary": "3-5 sentences in Chinese, actionable overview",
  "macro_view": "1 paragraph Chinese summary of macro agent",
  "equity_view": "1 paragraph Chinese summary of equity agent",
  "quant_view": "1 paragraph Chinese summary of quant agent",
  "themes": [
    {
      "name": "English",
      "name_zh": "中文",
      "thesis": "combined thesis in Chinese",
      "stage": "early"|"mid"|"late",
      "stage_label_zh": "早期|中期|晚期",
      "consensus_score": 0-1,
      "investability_score": 0-1,
      "agent_stages": {"macro": "early", "equity": "mid", "quant": "early"},
      "synthesis": "why final stage, 2-3 sentences Chinese",
      "key_drivers": [],
      "risks": [],
      "tickers_or_sectors": []
    }
  ]
}

Rules:
- Include 4-6 themes ranked by investability_score descending
- Final stage = weighted judgment; if agents disagree, explain in synthesis and lower consensus_score
- early = 布局期, mid = 主升/兑现期, late = 过热/退出观察期
- Be direct about what to invest NOW vs watch"""


class ThemeOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings.from_env()
        self._llm = LLMClient(self._settings)
        self._macro = MacroEconomist(self._llm, self._settings)
        self._equity = EquityResearchAnalyst(self._llm, self._settings)
        self._quant = QuantAnalyst(self._llm, self._settings)

    def run(self) -> InvestmentBrief:
        vol = fetch_vol_snapshot()

        macro = self._macro.analyze()
        equity = self._equity.analyze(macro)
        quant = self._quant.analyze(macro, equity, vol)

        brief = self._synthesize(macro, equity, quant)
        return self._enrich_stages(brief)

    def _synthesize(
        self, macro: MacroReport, equity: EquityReport, quant: QuantReport
    ) -> InvestmentBrief:
        payload = {
            "macro_report": macro.model_dump(),
            "equity_report": equity.model_dump(),
            "quant_report": quant.model_dump(),
        }
        user = f"""Synthesize the three agent reports into a unified CIO brief.

Reports:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Return ranked themes with final stage and per-agent stage breakdown."""
        return self._llm.structured(
            system=SYNTHESIS_SYSTEM, user=user, schema=InvestmentBrief, temperature=0.2
        )

    def _enrich_stages(self, brief: InvestmentBrief) -> InvestmentBrief:
        """Ensure stage_label_zh is set; merge rule-based consensus if LLM omitted."""
        themes: list[FinalTheme] = []
        for t in brief.themes:
            stage = t.stage if isinstance(t.stage, ThemeStage) else ThemeStage(t.stage)
            label = t.stage_label_zh or STAGE_ZH.get(stage, stage.value)
            themes.append(
                t.model_copy(
                    update={
                        "stage": stage,
                        "stage_label_zh": label,
                    }
                )
            )
        return brief.model_copy(update={"themes": themes})


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
