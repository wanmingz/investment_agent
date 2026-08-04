"""Reasoning agent — synthesizes four domain reports into ReasoningOutput."""

from __future__ import annotations

import json
from datetime import date

from investment_agent.dates import format_date_display, format_date_iso
from investment_agent.llm import LLMClient
from investment_agent.stock_research.models import (
    BusinessReport,
    ExpectationReport,
    FinancialReport,
    ReasoningOutput,
    ValuationReport,
)

SYSTEM = """You are the lead portfolio manager writing a single-stock INVESTMENT MEMO.

You receive four independent analyst reports (business, financial, valuation, expectation).
Synthesize them into a clear rating and thesis.

Rules:
- Write ALL output in English only.
- rating must be one of: buy | hold | sell | watch
- Do NOT invent numbers that do not appear in the four reports.
- Reconcile conflicts explicitly (e.g. great business but expensive / weak expectations).
- Be decision-oriented and concise.

Output valid JSON matching ReasoningOutput.
"""


class ReasoningAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(
        self,
        *,
        ticker: str,
        company_name: str,
        as_of: date,
        last_price: float | None,
        business: BusinessReport,
        financial: FinancialReport,
        valuation: ValuationReport,
        expectation: ExpectationReport,
    ) -> ReasoningOutput:
        price = "n/a" if last_price is None else f"{last_price:.2f}"
        payload = {
            "business": business.model_dump(mode="json"),
            "financial": financial.model_dump(mode="json"),
            "valuation": valuation.model_dump(mode="json"),
            "expectation": expectation.model_dump(mode="json"),
        }
        user = f"""Analysis as-of date: {format_date_display(as_of)} ({format_date_iso(as_of)}).
Ticker: {ticker}
Company: {company_name}
Last price: {price}
Respond in English only.

DOMAIN REPORTS (JSON):
{json.dumps(payload, ensure_ascii=False, indent=2)}

Produce a ReasoningOutput investment memo. Cite only facts present above."""
        return self._llm.structured(system=SYSTEM, user=user, schema=ReasoningOutput)
