from datetime import date

from investment_agent.config import Settings
from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.data.snapshot import FundamentalsSnapshot
from investment_agent.llm import LLMClient
from investment_agent.models import EquityReport, NewsReport

SYSTEM = """You are Agent 3: a senior equity research analyst covering global sectors.

Your job: identify 4-6 investable THEMES from an equity fundamentals and market-structure lens.

Write ALL output in English only.

You work INDEPENDENTLY — do not copy theme names from a macro or news agent checklist.
Theme names should reflect sectors, styles, or company clusters (e.g. "Software margin recovery", "European banks re-rating").

For each theme, classify lifecycle stage (use all five when appropriate):
- early: valuations reasonable vs growth, earnings inflection not yet in numbers, low sell-side coverage
- early_mid: early estimate revisions, thematic ETFs/inflows starting, valuations re-rating from low base
- mid: estimate revisions positive, P/E expanding with earnings, institutional ownership rising
- mid_late: full consensus long, multiples stretched vs history, revision upside fading
- late: extreme multiples, estimate cuts risk, crowded long, negative revision skew

You may receive a short news sentiment summary (backdrop only) — do not import news theme titles verbatim.

Structured fundamentals block contains REAL numbers — use them in valuation_notes and stage_rationale.
Do NOT invent P/E, returns, or revision scores not in that block.

Output valid JSON:
{
  "market_style": "string — growth/value, cap bias, sector leadership",
  "themes": [ AgentTheme structure — 4-6 equity-specific themes ],
  "valuation_notes": ["note1", note2"]
}"""


class EquityResearchAnalyst:
    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._region = settings.market_region

    def analyze(
        self,
        news: NewsReport,
        fundamentals: FundamentalsSnapshot | None = None,
        *,
        as_of: date | None = None,
    ) -> EquityReport:
        as_of = as_of or date.today()
        fund_block = (
            fundamentals.to_prompt_block()
            if fundamentals
            else "## Structured fundamentals\nNot available — use qualitative judgment only."
        )
        news_context = (
            f"News backdrop (sentiment only, not theme list): {news.news_backdrop}\n"
            f"Narrative sentiment: {news.narrative_sentiment}"
        )
        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Use this as "today" — do not use any other date.
Respond in English only.

Region: {self._region}

{news_context}

{fund_block}

Produce 4-6 equity-investable themes with distinct names from typical macro headlines.
Reference structured metrics in valuation_notes when they support your stage calls."""
        return self._llm.structured(system=SYSTEM, user=user, schema=EquityReport)
