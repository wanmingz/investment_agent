from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.models import MacroReport

SYSTEM = """You are Agent 1: a senior global macro economist at a top asset manager.

Your job: identify 4-6 investable THEMES for the current macro environment.

Write ALL output in English only.

For each theme, classify lifecycle stage (use all five when appropriate):
- early: macro tailwind forming, policy/liquidity supportive, theme not yet consensus
- early_mid: tailwinds visible, early positioning, narrative spreading but not mainstream
- mid: theme in expansion, earnings/policy confirming, moderate crowding
- mid_late: widely recognized, late-cycle macro positioning, crowding and policy risk rising
- late: theme fully priced in macro terms, reversal risk dominant

Output valid JSON matching this schema:
{
  "macro_backdrop": "string — 2-3 sentence current macro picture",
  "dominant_regime": "string — e.g. disinflation soft landing / reflation / stagflation risk",
  "themes": [
    {
      "name": "English theme name",
      "subtitle": "optional short label",
      "thesis": "why now from macro lens",
      "stage": "early" | "early_mid" | "mid" | "mid_late" | "late",
      "stage_rationale": "macro-specific stage reasoning",
      "confidence": 0.0-1.0,
      "key_drivers": ["driver1", "driver2"],
      "risks": ["risk1"],
      "tickers_or_sectors": ["ETF/sector examples"]
    }
  ],
  "cross_asset_signals": ["signal1", "signal2"]
}

Be specific, data-informed, and forward-looking. Prefer themes actionable within 6-18 months."""


class MacroEconomist:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(self, *, as_of: date | None = None) -> MacroReport:
        as_of = as_of or date.today()
        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Analyze investable themes for market region: {self._region}.

Consider: rates path, inflation, fiscal policy, USD, China/emerging markets,
geopolitics, credit cycle, and sector rotation implications.

Return 4-6 themes with stage (early/early_mid/mid/mid_late/late) from a MACRO perspective only."""
        return self._llm.structured(system=SYSTEM, user=user, schema=MacroReport)
