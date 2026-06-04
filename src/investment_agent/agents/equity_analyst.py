from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.models import EquityReport, MacroReport, NewsReport

SYSTEM = """You are Agent 2: a senior equity research analyst covering global sectors.

Your job: refine and validate investable THEMES from an equity fundamentals lens.

Write ALL output in English only.

For each theme, classify lifecycle stage (use all five when appropriate):
- early: valuations reasonable vs growth, earnings inflection not yet in numbers, low sell-side coverage
- early_mid: early estimate revisions, thematic ETFs/inflows starting, valuations re-rating from low base
- mid: estimate revisions positive, P/E expanding with earnings, institutional ownership rising
- mid_late: full consensus long, multiples stretched vs history, revision upside fading
- late: extreme multiples, estimate cuts risk, crowded long, negative revision skew

You will receive macro economist and news (RAG) reports — you may agree, disagree on stage, or add equity-specific themes.
News-backed drivers should align with cited headlines when relevant.

Output valid JSON:
{
  "market_style": "string — growth/value, cap bias, sector leadership",
  "themes": [ same AgentTheme structure as macro agent ],
  "valuation_notes": ["note1", "note2"]
}

Each theme object must include: name, subtitle, thesis, stage, stage_rationale, confidence, key_drivers, risks, tickers_or_sectors."""


class EquityResearchAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(
        self, macro: MacroReport, news: NewsReport, *, as_of: date | None = None
    ) -> EquityReport:
        as_of = as_of or date.today()
        macro_summary = macro.model_dump_json(indent=2)
        news_summary = news.model_dump_json(indent=2)
        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Region: {self._region}

Macro economist output (use as starting point, challenge stage if equity data disagrees):
{macro_summary}

News / RAG output (recent headlines with citations — factor into sector sentiment):
{news_summary}

Produce 4-6 equity-investable themes with stage (early/early_mid/mid/mid_late/late) from EQUITY RESEARCH perspective.
Include specific sectors, style factors, and example tickers/ETFs where relevant."""
        return self._llm.structured(system=SYSTEM, user=user, schema=EquityReport)
