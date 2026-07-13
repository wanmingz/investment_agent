"""Streamlit UI for AI / model portfolio (paper ledger)."""

from __future__ import annotations

import streamlit as st

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.ledger_streamlit import render_ledger
from investment_agent.portfolio.model import LEDGER
from investment_agent.portfolio.model.target_views import render_model_performance_section


def render(brief: InvestmentBrief | None) -> None:
    if brief is not None:
        render_model_performance_section(brief)
    else:
        st.info(
            "Load a theme brief (**Themes** → **Load last result** or run analysis) "
            "to see model portfolio performance and target weights."
        )
    render_ledger(
        brief,
        LEDGER,
        show_theme_alignment=False,
        skip_performance_compare=brief is not None,
    )
