"""Business analysis agent — one LLM call on BusinessInput only."""

from __future__ import annotations

from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research.business.input import BusinessInput
from investment_agent.stock_research.models import BusinessReport

SYSTEM = """You are a senior equity research analyst focused on BUSINESS QUALITY.

Analyze the company's business model, competitive position, and catalysts.
Write ALL output in English only.
Work INDEPENDENTLY — do not assume financial ratios, valuation multiples, or consensus targets
beyond what appears in the provided context block. Do not invent numbers.

Output valid JSON matching BusinessReport:
- company_overview, business_model, competitive_position
- key_segments, catalysts, business_risks
- quality_score (0-1)
"""


class BusinessAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: BusinessInput) -> BusinessReport:
        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Ticker: {inp.ticker}
Company: {inp.company_name}
Respond in English only.

CONTEXT BLOCK:
{inp.context_block}

Produce a BusinessReport grounded only in this context."""
        return self._llm.structured(system=SYSTEM, user=user, schema=BusinessReport)
