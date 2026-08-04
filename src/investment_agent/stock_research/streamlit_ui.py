"""Shared Streamlit UI for single-stock research (used by streamlit_app View → Stock)."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from investment_agent.llm import QuotaExhaustedError
from investment_agent.stock_research import checkpoint as stock_checkpoint
from investment_agent.stock_research.orchestrator import StockResearchOrchestrator
from investment_agent.stock_research.storage import (
    latest_path,
    list_latest_tickers,
    load_memo,
    save_run_reports,
)
from investment_agent.stock_research.views import render_agent_tabs, render_memo


@dataclass(frozen=True)
class StockSidebarState:
    ticker: str
    run_btn: bool
    resume: bool


def ensure_memo_state() -> None:
    if "memo" not in st.session_state:
        st.session_state.memo = None


def render_stock_sidebar() -> StockSidebarState:
    """Sidebar controls for Stock view (call inside ``st.sidebar``)."""
    ensure_memo_state()
    ticker = st.text_input("Ticker", value="AAPL", key="stock_ticker_input").strip().upper()
    resume = st.checkbox(
        "Resume stock checkpoint",
        value=stock_checkpoint.is_resume_enabled(),
        key="stock_resume_ckpt",
        help="Saves progress under reports/cache/stock_research/{TICKER}/",
    )
    steps = stock_checkpoint.list_checkpoint_steps(ticker) if ticker else []
    if steps:
        st.caption(f"Stock checkpoint: {', '.join(steps)}")
        if st.button("Clear stock checkpoint", use_container_width=True, key="stock_clear_ckpt"):
            stock_checkpoint.clear_checkpoint(ticker)
            st.rerun()

    run_btn = st.button(
        "🔎 Run stock research",
        type="primary",
        use_container_width=True,
        key="stock_run_btn",
    )
    st.caption("Takes several minutes (~5 LLM calls).")

    if ticker and latest_path(ticker).is_file():
        st.success(f"Saved memo for {ticker}")
        if st.button("📂 Load last memo", use_container_width=True, key="stock_load_last"):
            loaded = load_memo(ticker)
            if loaded is not None:
                st.session_state.memo = loaded
            st.rerun()

    others = [t for t in list_latest_tickers() if t != ticker]
    if others:
        pick = st.selectbox("Other saved tickers", [""] + others, key="stock_other_ticker")
        if pick and st.button("Load selected memo", use_container_width=True, key="stock_load_pick"):
            st.session_state.memo = load_memo(pick)
            st.rerun()

    return StockSidebarState(ticker=ticker, run_btn=run_btn, resume=resume)


def maybe_run_stock_research(state: StockSidebarState) -> None:
    if not state.run_btn:
        return
    if not state.ticker:
        st.error("Enter a ticker.")
        st.stop()
    try:
        from investment_agent.streamlit_llm import settings_from_sidebar

        settings = settings_from_sidebar(market_region="global")
    except ValueError as e:
        st.error(str(e))
        st.stop()

    with st.status(f"Researching {state.ticker}…", expanded=True) as status:
        st.write("Fetch data bundle")
        st.write("Business · Financial · Valuation · Expectation")
        st.write("Reasoning → investment memo")
        try:
            memo = StockResearchOrchestrator(settings).run(
                state.ticker, resume=state.resume
            )
            latest, archive = save_run_reports(memo)
            st.session_state.memo = memo
            status.update(label="Research complete", state="complete")
            st.success(f"Saved `{latest}` · `{archive}`")
        except QuotaExhaustedError as e:
            status.update(label="API quota exceeded", state="error")
            st.error(e.user_hint())
            left = stock_checkpoint.list_checkpoint_steps(state.ticker)
            if left:
                st.info(f"Progress saved: {', '.join(left)}. Resume and retry later.")
            st.stop()
        except Exception as e:  # noqa: BLE001
            status.update(label="Research failed", state="error")
            st.error(f"Run failed: {e}")
            left = stock_checkpoint.list_checkpoint_steps(state.ticker)
            if left:
                st.warning(f"Partial checkpoint: {', '.join(left)}")
            st.stop()


def render_stock_page_body() -> None:
    ensure_memo_state()
    st.markdown(
        '<p class="main-header">🔎 Single-Stock Research</p>'
        '<p style="color:#64748b;margin:-0.5rem 0 1rem;">'
        "Business · Financial · Valuation · Expectation → Investment Memo"
        "</p>",
        unsafe_allow_html=True,
    )
    memo = st.session_state.get("memo")
    if memo is None:
        st.info(
            "Enter a ticker and click **Run stock research**, or load a saved memo. "
            "Friends: open **Your LLM API key** in the sidebar to use your own key."
        )
        return
    render_memo(memo)
    st.divider()
    st.subheader("Domain agent reports")
    render_agent_tabs(memo)


def standalone_main() -> None:
    """Full-page entry used by ``stock_research_app.py``."""
    from investment_agent.streamlit_llm import (
        render_active_llm_caption,
        render_visitor_llm_sidebar,
    )

    st.set_page_config(
        page_title="Single-Stock Research",
        page_icon="🔎",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    with st.sidebar:
        st.header("Controls")
        state = render_stock_sidebar()
        st.divider()
        render_visitor_llm_sidebar()
        render_active_llm_caption()
    maybe_run_stock_research(state)
    render_stock_page_body()
