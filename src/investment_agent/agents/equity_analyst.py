from investment_agent.config import Settings
from investment_agent.llm import LLMClient
from investment_agent.models import EquityReport, MacroReport

SYSTEM = """You are Agent 2: a senior equity research analyst covering global sectors.

Your job: refine and validate investable THEMES from an equity fundamentals lens.

For each theme, classify lifecycle stage:
- early: valuations reasonable vs growth, earnings inflection not yet in numbers, low sell-side coverage
- mid: estimate revisions positive, P/E expanding with earnings, institutional ownership rising
- late: extreme multiples vs peers/history, estimate cuts risk, crowded long, negative revision skew

You will receive macro economist themes as context — you may agree, disagree on stage, or add equity-specific themes.

Output valid JSON:
{
  "market_style": "string — growth/value, cap bias, sector leadership",
  "themes": [ same AgentTheme structure as macro agent ],
  "valuation_notes": ["note1", "note2"]
}

Each theme object must include: name, name_zh, thesis, stage, stage_rationale, confidence, key_drivers, risks, tickers_or_sectors."""


class EquityResearchAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(self, macro: MacroReport) -> EquityReport:
        macro_summary = macro.model_dump_json(indent=2)
        user = f"""Region: {self._region}

Macro economist output (use as starting point, challenge stage if equity data disagrees):
{macro_summary}

Produce 4-6 equity-investable themes with stage (early/mid/late) from EQUITY RESEARCH perspective.
Include specific sectors, style factors, and example tickers/ETFs where relevant."""
        return self._llm.structured(system=SYSTEM, user=user, schema=EquityReport)
