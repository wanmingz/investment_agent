"""Streamlit UI for My portfolio (manual ledger)."""

from __future__ import annotations

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.ledger_streamlit import render_ledger
from investment_agent.portfolio.manual import LEDGER


def render(brief: InvestmentBrief | None) -> None:
    render_ledger(brief, LEDGER, show_theme_alignment=True)
