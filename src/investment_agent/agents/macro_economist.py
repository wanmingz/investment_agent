from investment_agent.config import Settings
from investment_agent.llm import LLMClient
from investment_agent.models import MacroReport

SYSTEM = """You are Agent 1: a senior global macro economist at a top asset manager.

Your job: identify 4-6 investable THEMES for the current macro environment.

For each theme, classify lifecycle stage:
- early: macro tailwind forming, policy/liquidity supportive, theme not yet consensus
- mid: theme in expansion, earnings/policy confirming, moderate crowding
- late: theme fully priced in macro terms, late-cycle positioning, reversal risk rising

Output valid JSON matching this schema:
{
  "macro_backdrop": "string — 2-3 sentence current macro picture",
  "dominant_regime": "string — e.g. disinflation soft landing / reflation / stagflation risk",
  "themes": [
    {
      "name": "English theme name",
      "name_zh": "中文主题名",
      "thesis": "why now from macro lens",
      "stage": "early" | "mid" | "late",
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

    def analyze(self) -> MacroReport:
        user = f"""Analyze investable themes as of today for market region: {self._region}.

Consider: rates path, inflation, fiscal policy, USD, China/emerging markets,
geopolitics, credit cycle, and sector rotation implications.

Return 4-6 themes with stage (early/mid/late) from a MACRO perspective only."""
        return self._llm.structured(system=SYSTEM, user=user, schema=MacroReport)
