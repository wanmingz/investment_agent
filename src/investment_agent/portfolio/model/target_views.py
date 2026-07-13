"""Target allocation and performance for model portfolio."""

from __future__ import annotations

import streamlit as st

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.ledger_streamlit_charts import render_model_target_performance
from investment_agent.portfolio.model.allocation import compute_model_target_allocation
from investment_agent.portfolio.model.target_performance import target_allocation_performance_series


def render_model_performance_section(brief: InvestmentBrief) -> None:
    """Score-weighted benchmark targets + indexed performance vs SPY (no trade ledger)."""
    st.caption(
        "Research-only model portfolio from the latest brief. "
        "Record real trades under **My portfolio**."
    )
    target = compute_model_target_allocation(brief)
    if not target.rows:
        st.info("No sector benchmarks mapped from top brief themes.")
        return

    target_points = target_allocation_performance_series(target)
    if target_points:
        last = target_points[-1]
        port_ret = last.portfolio_index - 100.0
        spy_ret = last.spy_index - 100.0
        m1, m2, m3 = st.columns(3)
        m1.metric("Model return (indexed)", f"{port_ret:+.1f}%")
        m2.metric("SPY (same window)", f"{spy_ret:+.1f}%")
        m3.metric("vs SPY", f"{port_ret - spy_ret:+.1f} pp")

    render_model_target_performance(
        target_points,
        ledger_points=None,
        as_of_label=target.as_of.isoformat(),
    )

    with st.expander("Benchmark weights (sector ETFs / SPY)", expanded=False):
        table_rows = [
            {
                "ETF": row.symbol,
                "Target %": f"{row.target_pct:.1f}",
                "Themes": ", ".join(row.source_themes),
            }
            for row in target.rows
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
        st.caption(f"Total target weight: **{target.total_target_pct:.1f}%**")
