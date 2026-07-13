"""Shared Streamlit ledger UI for manual and model portfolios."""

from __future__ import annotations

import streamlit as st

from investment_agent.dates import analysis_date
from investment_agent.models import InvestmentBrief
from investment_agent.portfolio import db as portfolio_db
from investment_agent.portfolio.db import LedgerKind
from investment_agent.portfolio.ledger import (
    InsufficientSharesError,
    InvalidDeleteError,
    TradeNotFoundError,
    add_trade,
    delete_trade,
    list_trades,
)
from investment_agent.portfolio.ledger_streamlit_charts import (
    render_performance_compare,
    render_position_pie,
)
from investment_agent.portfolio.manual.theme_alignment import compute_theme_alignment
from investment_agent.portfolio.models import (
    TradeInput,
    TradeSide,
    model_name,
    snapshot_cash_balance,
    snapshot_total_nav,
)
from investment_agent.portfolio.performance import summarize_performance
from investment_agent.portfolio.quotes import fetch_close_on_date, fetch_symbol_name
from investment_agent.universe.symbols import is_likely_ticker

_LEDGER_LABELS: dict[LedgerKind, str] = {
    "manual": "My portfolio (manual)",
    "model": "Paper / model ledger",
}


def _render_theme_alignment(brief: InvestmentBrief, snapshot) -> None:
    st.markdown("#### Research alignment")
    st.caption(
        "Top themes from the latest brief vs your open positions (ticker + sector ETF match). "
        "Read-only — does not change analysis or trades."
    )
    report = compute_theme_alignment(brief, snapshot)
    if not report.rows:
        st.caption("_No themes in brief._")
        return

    status_labels = {"high": "High overlap", "partial": "Partial", "gap": "Gap (no holdings)"}
    table_rows = []
    for row in report.rows:
        symbols = ", ".join(row.overlap_symbols) if row.overlap_symbols else "—"
        table_rows.append(
            {
                "Rank": row.rank,
                "Theme": row.theme_name,
                "Overlap": symbols,
                "% of NAV": f"{row.overlap_pct:.1f}%",
                "Status": status_labels.get(row.status, row.status),
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    if report.gap_themes:
        st.caption(
            "**Research gaps (themes without holdings):** " + ", ".join(report.gap_themes)
        )
    if report.uncovered_positions:
        uncovered = ", ".join(
            f"{p.symbol} ({p.weight_pct:.1f}%)" for p in report.uncovered_positions
        )
        st.caption(f"**Holdings not covered by top themes:** {uncovered}")


def render_ledger(
    brief: InvestmentBrief | None,
    ledger: LedgerKind,
    *,
    show_theme_alignment: bool,
    skip_performance_compare: bool = False,
) -> None:
    """Trade form, metrics, positions, and optional theme alignment for one ledger."""
    st.markdown(f"##### {_LEDGER_LABELS[ledger]}")
    st.caption(f"Ledger: `{portfolio_db.db_path(ledger)}`")

    key_prefix = ledger

    st.markdown("#### Record trade")
    c_sym, c_date = st.columns(2)
    with c_sym:
        symbol_raw = st.text_input(
            "Symbol",
            placeholder="AAPL",
            key=f"portfolio_trade_symbol_{key_prefix}",
        )
        symbol = symbol_raw.strip().upper()
    with c_date:
        trade_date = st.date_input(
            "Trade date",
            value=analysis_date(),
            key=f"portfolio_trade_date_{key_prefix}",
        )

    close_price: float | None = None
    symbol_name = ""
    if symbol:
        if is_likely_ticker(symbol):
            with st.spinner("Loading quote…"):
                close_price = fetch_close_on_date(symbol, trade_date)
                symbol_name = fetch_symbol_name(symbol)
            if close_price is not None:
                st.caption(
                    f"Close on {trade_date.isoformat()}: **${close_price:.2f}** (editable below)"
                )
            else:
                st.caption("Close price unavailable — enter price manually.")
            if symbol_name:
                st.caption(f"**{symbol_name}** ({symbol})")
        else:
            st.caption("Enter a valid ticker (e.g. AAPL) to load name and close price.")

    default_price = close_price if close_price is not None else 100.0

    with st.form(f"add_trade_form_{key_prefix}", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            side = st.selectbox("Side", ["buy", "sell"])
            name = st.text_input(
                "Name",
                value=symbol_name,
                help="Auto-filled from yfinance; editable.",
            )
        with c2:
            quantity = st.number_input("Quantity", min_value=0.0001, value=1.0, step=1.0)
            price = st.number_input(
                "Price ($)",
                min_value=0.01,
                value=float(default_price),
                step=0.01,
                help="Prefilled from market close; override if needed.",
            )
        with c3:
            fees = st.number_input("Fees ($)", min_value=0.0, value=0.0, step=0.01)
            notes = st.text_input("Notes (optional)", "")
        submitted = st.form_submit_button("Save trade", type="primary")

    if submitted:
        if not symbol:
            st.error("Symbol is required.")
        else:
            try:
                trade = TradeInput(
                    symbol=symbol,
                    side=TradeSide(side),
                    quantity=float(quantity),
                    price=float(price),
                    trade_date=trade_date,
                    name=name.strip(),
                    fees=float(fees),
                    notes=notes,
                )
                stored = add_trade(trade, ledger=ledger)
                label = (
                    f"{model_name(stored)} ({stored.symbol})"
                    if model_name(stored)
                    else stored.symbol
                )
                st.success(
                    f"Recorded {stored.side.value} {stored.quantity:g} {label} "
                    f"@ ${stored.price:.2f} on {stored.trade_date.isoformat()}"
                )
            except InsufficientSharesError as e:
                st.error(str(e))
            except ValueError as e:
                st.error(str(e))

    try:
        summary = summarize_performance(ledger=ledger)
    except RuntimeError as e:
        st.error(f"Database error: {e}")
        return

    if summary.first_trade_date is None:
        st.info("No trades yet. Use the form above to record your first trade.")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Portfolio value", f"${snapshot_total_nav(summary.snapshot):,.2f}")
    m2.metric("Net invested", f"${summary.gross_invested:,.2f}")
    m3.metric("Total P&L", f"${summary.total_pnl:,.2f}")
    m4.metric(
        "Total return",
        f"{summary.total_return_pct:.1f}%" if summary.total_return_pct is not None else "—",
        help="(Portfolio value − net invested) ÷ net invested. "
        "Net invested counts only new cash for buys; sell proceeds can be reinvested.",
    )
    m5.metric(
        "vs SPY",
        f"{summary.vs_spy_pct:+.1f} pp" if summary.vs_spy_pct is not None else "—",
    )

    cash_bal = snapshot_cash_balance(summary.snapshot)
    cash_line = (
        f"Cash ${cash_bal:,.2f} · "
        if cash_bal > 0.01
        else ""
    )
    st.caption(
        f"{cash_line}"
        f"Holdings ${summary.snapshot.total_market_value:,.2f} · "
        f"Realized ${summary.realized_pnl:,.2f} · "
        f"Unrealized ${summary.snapshot.total_unrealized_pnl:,.2f} · "
        f"SPY {summary.spy_return_pct:.1f}% since {summary.first_trade_date.isoformat()}"
        if summary.spy_return_pct is not None
        else f"{cash_line}"
        f"Holdings ${summary.snapshot.total_market_value:,.2f} · "
        f"Realized ${summary.realized_pnl:,.2f} · "
        f"Unrealized ${summary.snapshot.total_unrealized_pnl:,.2f}"
    )

    if not skip_performance_compare:
        render_performance_compare(ledger=ledger)

    st.markdown("#### Open positions")
    if summary.snapshot.positions:
        col_table, col_chart = st.columns([3, 2])
        with col_table:
            rows = []
            for p in summary.snapshot.positions:
                rows.append(
                    {
                        "Name": model_name(p) or "—",
                        "Symbol": p.symbol,
                        "Qty": p.quantity,
                        "Avg cost": p.avg_cost,
                        "Last": p.last_price,
                        "Market value": p.market_value,
                        "Unrealized P&L": p.unrealized_pnl,
                        "Unrealized %": p.unrealized_pnl_pct,
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
        with col_chart:
            st.markdown("##### Allocation")
            st.caption("By market value")
            render_position_pie(summary.snapshot.positions, cash=cash_bal)
    else:
        cash = cash_bal
        if cash > 0.01:
            st.caption(f"_All positions closed._ Cash balance: **${cash:,.2f}**")
        else:
            st.caption("_All positions closed._")

    if show_theme_alignment and brief is not None and summary.snapshot.positions:
        _render_theme_alignment(brief, summary.snapshot)
    elif show_theme_alignment and brief is None and summary.snapshot.positions:
        st.info(
            "Load a theme brief (**Themes** → **Load last result** or run analysis) "
            "to see research alignment with your holdings."
        )

    trades = list_trades(ledger=ledger)
    if trades:
        with st.expander(f"Trade history ({len(trades)})", expanded=False):
            pending_key = f"pending_delete_trade_id_{key_prefix}"
            pending_id = st.session_state.get(pending_key)
            if pending_id is not None:
                pending = next((t for t in trades if t.id == pending_id), None)
                if pending is None:
                    st.session_state[pending_key] = None
                else:
                    st.warning(
                        f"Delete trade **#{pending.id}**? "
                        f"{pending.side.value} {pending.quantity:g} {pending.symbol} "
                        f"@ ${pending.price:.2f} on {pending.trade_date.isoformat()}"
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Confirm delete",
                            type="primary",
                            key=f"confirm_delete_trade_{key_prefix}",
                        ):
                            try:
                                delete_trade(pending.id, ledger=ledger)
                                st.session_state[pending_key] = None
                                st.success(f"Deleted trade #{pending.id}")
                                st.rerun()
                            except (TradeNotFoundError, InvalidDeleteError) as e:
                                st.error(str(e))
                    with c2:
                        if st.button("Cancel", key=f"cancel_delete_trade_{key_prefix}"):
                            st.session_state[pending_key] = None
                            st.rerun()

            for t in reversed(trades):
                sym_label = (
                    f"{model_name(t)} ({t.symbol})" if model_name(t) else t.symbol
                )
                label = (
                    f"#{t.id} · {t.trade_date.isoformat()} · {t.side.value} · "
                    f"{t.quantity:g} {sym_label} @ ${t.price:.2f}"
                )
                if t.notes:
                    label += f" · {t.notes}"
                row1, row2 = st.columns([5, 1])
                with row1:
                    st.text(label)
                with row2:
                    if st.button("Delete", key=f"delete_trade_{key_prefix}_{t.id}"):
                        st.session_state[pending_key] = t.id
                        st.rerun()
