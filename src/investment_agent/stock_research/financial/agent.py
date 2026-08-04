"""Financial analysis agent — one LLM call on FinancialInput only."""

from __future__ import annotations

from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research.financial.input import FinancialInput
from investment_agent.stock_research.models import FinancialReport

SYSTEM = """You are a senior equity research analyst focused on FINANCIAL STATEMENT QUALITY.

Assess growth, profitability, balance sheet strength, and cash flow using ONLY numbers in the
context block. Write ALL output in English only.
Work INDEPENDENTLY — ignore valuation multiples and Street targets unless present in the block.
Do not invent metrics.

Output valid JSON matching FinancialReport.
"""


class FinancialAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: FinancialInput) -> FinancialReport:
        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Ticker: {inp.ticker}
Company: {inp.company_name}
Respond in English only.

CONTEXT BLOCK:
{inp.context_block}

Produce a FinancialReport grounded only in this context."""
        return self._llm.structured(system=SYSTEM, user=user, schema=FinancialReport)
