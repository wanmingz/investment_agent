"""Business agent input builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from investment_agent.stock_research.bundle import StockBundle


@dataclass(frozen=True)
class BusinessInput:
    ticker: str
    as_of: date
    company_name: str
    context_block: str


def build_business_input(bundle: StockBundle) -> BusinessInput:
    return BusinessInput(
        ticker=bundle.ticker,
        as_of=bundle.as_of,
        company_name=bundle.company_name,
        context_block=bundle.business_block,
    )
