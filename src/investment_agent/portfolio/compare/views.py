"""Streamlit UI for Compare (manual vs brief target)."""

from __future__ import annotations

import streamlit as st

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.compare import VIEW_LABEL
from investment_agent.portfolio.compare.service import evaluate_manual_vs_target


def render(brief: InvestmentBrief | None) -> None:
    st.markdown(f"#### {VIEW_LABEL} — manual vs model benchmark")
    st.caption(
        "Your real portfolio vs score-weighted sector ETF targets (same as Model portfolio). "
        "Single stocks roll up to the ETF of their highest-ranked matching theme. Read-only."
    )

    outcome = evaluate_manual_vs_target(brief)
    if outcome.status == "ok" and outcome.table_rows:
        st.dataframe(outcome.table_rows, use_container_width=True, hide_index=True)
        if outcome.uncovered_pct is not None:
            st.caption(
                f"**Unmapped holdings:** {outcome.uncovered_pct:.1f}% of NAV "
                "(no overlap with top brief themes)."
            )
        return
    if outcome.status == "empty" and not outcome.message:
        st.caption("_No drift rows._")
        return
    if outcome.message:
        if outcome.status in ("no_brief", "no_trades"):
            st.info(outcome.message)
        elif outcome.status == "empty":
            st.error(outcome.message)
        else:
            st.caption(outcome.message)
