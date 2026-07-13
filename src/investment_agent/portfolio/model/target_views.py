"""Target allocation and performance for model portfolio."""

from __future__ import annotations

import streamlit as st

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.model.allocation import compute_model_target_allocation
from investment_agent.portfolio.compare.drift import compute_benchmark_drift_report
from investment_agent.portfolio.ledger_streamlit_charts import render_model_target_performance
from investment_agent.portfolio.model import LEDGER
from investment_agent.portfolio.model.target_performance import model_performance_series
from investment_agent.portfolio.performance import summarize_performance


def render_model_performance_section(brief: InvestmentBrief) -> None:
    """Score-weighted target allocation + indexed performance vs SPY."""
    target = compute_model_target_allocation(brief)
    if not target.rows:
        st.info("No sector benchmarks mapped from top brief themes.")
        return

    target_points, ledger_points = model_performance_series(target, ledger=LEDGER)
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
        ledger_points=ledger_points,
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

    try:
        summary = summarize_performance(ledger=LEDGER)
    except RuntimeError:
        return
    if summary.first_trade_date is None:
        return

    report, uncovered = compute_benchmark_drift_report(brief, summary.snapshot, target)
    if not report.rows:
        return

    st.markdown("#### Paper ledger drift vs benchmark")
    drift_rows = [
        {
            "ETF": row.symbol,
            "Target %": f"{row.target_pct:.1f}",
            "Actual %": f"{row.actual_pct:.1f}",
            "Drift (pp)": f"{row.drift_pp:+.1f}",
            "Status": row.severity,
        }
        for row in report.rows
        if row.target_pct > 0 or row.actual_pct > 0
    ]
    if drift_rows:
        st.dataframe(drift_rows, use_container_width=True, hide_index=True)
    if uncovered > 0.01:
        st.caption(
            f"**Unmapped holdings:** {uncovered:.1f}% of NAV "
            "(no overlap with top brief themes)."
        )
