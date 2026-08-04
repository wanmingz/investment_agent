"""Single-stock research dashboard — run: streamlit run stock_research_app.py"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from investment_agent.config import Settings
from investment_agent.llm import QuotaExhaustedError
from investment_agent.stock_research import checkpoint
from investment_agent.stock_research.orchestrator import StockResearchOrchestrator
from investment_agent.stock_research.storage import (
    latest_path,
    list_latest_tickers,
    load_memo,
    save_run_reports,
)
from investment_agent.stock_research.views import render_agent_tabs, render_memo

st.set_page_config(
    page_title="Single-Stock Research",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    st.markdown(
        '<p style="font-size:1.6rem;font-weight:700;margin:0;">Single-Stock Research</p>'
        '<p style="color:#64748b;margin:0.25rem 0 1rem;">'
        "Business · Financial · Valuation · Expectation → Investment Memo"
        "</p>",
        unsafe_allow_html=True,
    )

    if "memo" not in st.session_state:
        st.session_state.memo = None

    with st.sidebar:
        st.header("Controls")
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        resume_ckpt = st.checkbox(
            "Resume from checkpoint",
            value=checkpoint.is_resume_enabled(),
            help="Saves progress under reports/cache/stock_research/{TICKER}/",
        )
        steps = checkpoint.list_checkpoint_steps(ticker) if ticker else []
        if steps:
            st.caption(f"Checkpoint: {', '.join(steps)}")
            if st.button("Clear checkpoint", use_container_width=True):
                checkpoint.clear_checkpoint(ticker)
                st.rerun()

        run_btn = st.button("Run research", type="primary", use_container_width=True)
        st.caption("Takes several minutes (~5 LLM calls).")

        if ticker and latest_path(ticker).is_file():
            st.success(f"Saved memo for {ticker}")
            if st.button("Load last memo", use_container_width=True):
                loaded = load_memo(ticker)
                if loaded is not None:
                    st.session_state.memo = loaded
                st.rerun()

        others = [t for t in list_latest_tickers() if t != ticker]
        if others:
            pick = st.selectbox("Other saved tickers", [""] + others)
            if pick and st.button("Load selected", use_container_width=True):
                st.session_state.memo = load_memo(pick)
                st.rerun()

        st.divider()
        try:
            s = Settings.from_env()
            st.text(f"Model: {s.provider}\n{s.model}")
        except ValueError as e:
            st.warning(str(e))

    if run_btn:
        if not ticker:
            st.error("Enter a ticker.")
            st.stop()
        try:
            settings = Settings.from_env()
        except ValueError as e:
            st.error(str(e))
            st.stop()

        with st.status(f"Researching {ticker}…", expanded=True) as status:
            st.write("Fetch data bundle")
            st.write("Business · Financial · Valuation · Expectation")
            st.write("Reasoning → investment memo")
            try:
                memo = StockResearchOrchestrator(settings).run(ticker, resume=resume_ckpt)
                latest, archive = save_run_reports(memo)
                st.session_state.memo = memo
                status.update(label="Research complete", state="complete")
                st.success(f"Saved `{latest}` · `{archive}`")
            except QuotaExhaustedError as e:
                status.update(label="API quota exceeded", state="error")
                st.error(e.user_hint())
                left = checkpoint.list_checkpoint_steps(ticker)
                if left:
                    st.info(f"Progress saved: {', '.join(left)}. Resume and retry later.")
                st.stop()
            except Exception as e:  # noqa: BLE001
                status.update(label="Research failed", state="error")
                st.error(f"Run failed: {e}")
                left = checkpoint.list_checkpoint_steps(ticker)
                if left:
                    st.warning(f"Partial checkpoint: {', '.join(left)}")
                st.stop()

    memo = st.session_state.get("memo")
    if memo is None:
        st.info("Enter a ticker and click **Run research**, or load a saved memo.")
        return

    render_memo(memo)
    st.divider()
    st.subheader("Domain agent reports")
    render_agent_tabs(memo)


if __name__ == "__main__":
    main()
