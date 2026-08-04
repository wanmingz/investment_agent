"""Streamlit render helpers for stock research memos."""

from __future__ import annotations

import streamlit as st

from investment_agent.stock_research.models import InvestmentMemo, MemoRating

_RATING_COLORS = {
    MemoRating.BUY: "#10b981",
    MemoRating.HOLD: "#f59e0b",
    MemoRating.SELL: "#ef4444",
    MemoRating.WATCH: "#6366f1",
}


def render_memo(memo: InvestmentMemo) -> None:
    color = _RATING_COLORS.get(memo.rating, "#64748b")
    price = "—" if memo.last_price is None else f"{memo.last_price:,.2f}"
    st.markdown(
        f"""
        <div style="margin-bottom:1rem;">
          <p style="font-size:1.75rem;font-weight:700;margin:0;">
            {memo.ticker}
            <span style="font-size:1rem;font-weight:500;color:#64748b;">
              {memo.company_name}
            </span>
          </p>
          <p style="margin:0.35rem 0 0;">
            <span style="background:{color};color:white;padding:0.2rem 0.6rem;
              border-radius:4px;font-weight:600;text-transform:uppercase;">
              {memo.rating.value}
            </span>
            <span style="margin-left:0.75rem;color:#64748b;">
              Confidence {memo.confidence:.0%} · Price {price}
            </span>
          </p>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0.4rem 0 0;">
            {memo.as_of_context or memo.report_date}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Executive summary")
    st.write(memo.executive_summary)
    st.subheader("Investment thesis")
    st.write(memo.investment_thesis)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Bull case**")
        for x in memo.bull_case or ["—"]:
            st.markdown(f"- {x}")
        st.markdown("**Catalysts**")
        for x in memo.catalysts or ["—"]:
            st.markdown(f"- {x}")
    with c2:
        st.markdown("**Bear case**")
        for x in memo.bear_case or ["—"]:
            st.markdown(f"- {x}")
        st.markdown("**Key risks**")
        for x in memo.key_risks or ["—"]:
            st.markdown(f"- {x}")

    if memo.valuation_takeaway:
        st.markdown("**Valuation takeaway**")
        st.write(memo.valuation_takeaway)
    if memo.expectation_takeaway:
        st.markdown("**Expectation takeaway**")
        st.write(memo.expectation_takeaway)
    if memo.monitoring_items:
        st.markdown("**Monitor**")
        for x in memo.monitoring_items:
            st.markdown(f"- {x}")

    if memo.data_sources:
        with st.expander("Data sources"):
            for s in memo.data_sources:
                st.caption(s)


def render_agent_tabs(memo: InvestmentMemo) -> None:
    tabs = st.tabs(["Business", "Financial", "Valuation", "Expectation", "Raw JSON"])
    with tabs[0]:
        if memo.business:
            st.write(memo.business.model_dump(mode="json"))
        else:
            st.info("No business report attached.")
    with tabs[1]:
        if memo.financial:
            st.write(memo.financial.model_dump(mode="json"))
        else:
            st.info("No financial report attached.")
    with tabs[2]:
        if memo.valuation:
            st.write(memo.valuation.model_dump(mode="json"))
        else:
            st.info("No valuation report attached.")
    with tabs[3]:
        if memo.expectation:
            st.write(memo.expectation.model_dump(mode="json"))
        else:
            st.info("No expectation report attached.")
    with tabs[4]:
        st.json(memo.model_dump(mode="json"))
