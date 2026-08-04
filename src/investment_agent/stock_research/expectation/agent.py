"""Expectation / consensus agent — one LLM call on ExpectationInput only."""

from __future__ import annotations

from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research.expectation.input import ExpectationInput
from investment_agent.stock_research.models import ExpectationReport

SYSTEM = """You are a senior equity analyst focused on MARKET EXPECTATIONS.

Explain what consensus and price targets imply, revision trends, and surprise potential.
Use ONLY figures in the context block. Write ALL output in English only.
Work INDEPENDENTLY — do not restate full valuation multiple tables unless present here.
Do not invent analyst counts or targets.

Output valid JSON matching ExpectationReport.
"""


class ExpectationAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(self, inp: ExpectationInput) -> ExpectationReport:
        price = "n/a" if inp.last_price is None else f"{inp.last_price:.2f}"
        user = f"""Analysis as-of date: {format_date_display(inp.as_of)} ({format_date_iso(inp.as_of)}).
Ticker: {inp.ticker}
Company: {inp.company_name}
Last price: {price}
Respond in English only.

CONTEXT BLOCK:
{inp.context_block}

Produce an ExpectationReport grounded only in this context."""
        return self._llm.structured(system=SYSTEM, user=user, schema=ExpectationReport)
