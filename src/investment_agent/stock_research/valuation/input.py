"""Valuation agent input builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from investment_agent.stock_research.bundle import StockBundle


@dataclass(frozen=True)
class ValuationInput:
    ticker: str
    as_of: date
    company_name: str
    last_price: float | None
    context_block: str


def build_valuation_input(bundle: StockBundle) -> ValuationInput:
    return ValuationInput(
        ticker=bundle.ticker,
        as_of=bundle.as_of,
        company_name=bundle.company_name,
        last_price=bundle.last_price,
        context_block=bundle.valuation_block,
    )
