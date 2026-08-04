"""Valuation analysis agent — one LLM call on ValuationInput only."""

from __future__ import annotations

from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research.models import ValuationReport
from investment_agent.stock_research.valuation.input import ValuationInput

SYSTEM = """You are a senior equity valuation analyst.

Judge whether the stock looks cheap, fair, or expensive using ONLY multiples and price stats
in the context block. Write ALL output in English only.
Do not invent peer multiples or DCF outputs not provided.
Work INDEPENDENTLY of business narrative and Street targets unless they appear in the block.

valuation_stance must be one of: cheap | fair | expensive | unclear

Output valid JSON matching ValuationReport.
"""


class ValuationAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: ValuationInput) -> ValuationReport:
        price = "n/a" if inp.last_price is None else f"{inp.last_price:.2f}"
        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Ticker: {inp.ticker}
Company: {inp.company_name}
Last price: {price}
Respond in English only.

CONTEXT BLOCK:
{inp.context_block}

Produce a ValuationReport grounded only in this context."""
        return self._llm.structured(system=SYSTEM, user=user, schema=ValuationReport)
