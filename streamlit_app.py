"""Investment theme dashboard — run: streamlit run streamlit_app.py"""

from __future__ import annotations

import html
import sys
from datetime import date as date_cls
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from investment_agent.storage import (
    brief_agent_themes,
    brief_data_sources,
    brief_fundamentals_notes,
    brief_narrative_citations,
    brief_narrative_view,
    theme_drivers_sourced,
    theme_risks_sourced,
)
from investment_agent.models import (
    AGENT_LABELS,
    AGENT_MARKETS,
    AGENT_NARRATIVE,
    AGENT_REGIME,
    STAGE_LABELS,
    STAGE_ORDER,
    AgentTheme,
    FinalTheme,
    InvestmentBrief,
    coerce_theme_stage,
    stage_label,
)
from investment_agent import checkpoint
from investment_agent.config import Settings
from investment_agent.dates import analysis_date, format_date_iso
from investment_agent.llm import QuotaExhaustedError
from investment_agent.orchestrator import ThemeOrchestrator
from investment_agent.portfolio.quotes import fetch_close_on_date, fetch_symbol_name
from investment_agent.universe.symbols import is_likely_ticker
from investment_agent.storage import DEFAULT_REPORT_PATH, load_brief, save_run_reports
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
from investment_agent.portfolio.models import (
    TradeInput,
    TradeSide,
    model_name,
    snapshot_cash_balance,
    snapshot_total_nav,
)
from investment_agent.portfolio.performance import (
    DEFAULT_COMPARE_START,
    compare_performance_series,
    summarize_performance,
)
from investment_agent.portfolio.theme_alignment import compute_theme_alignment

try:
    from investment_agent.dates import format_date_display
except ImportError:
    def format_date_display(d: date_cls | None = None) -> str:
        d = d or analysis_date()
        return d.strftime("%B %d, %Y")


st.set_page_config(
    page_title="Investment Theme Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

STAGE_COLORS: dict[str, tuple[str, str]] = {
    "early": ("#10b981", "#064e3b"),
    "early_mid": ("#34d399", "#065f46"),
    "mid": ("#f59e0b", "#78350f"),
    "mid_late": ("#fb923c", "#7c2d12"),
    "late": ("#ef4444", "#7f1d1d"),
}

_AGENT_DISPLAY_ORDER = (AGENT_REGIME, AGENT_NARRATIVE, AGENT_MARKETS)


def _agent_label(key: str) -> str:
    return AGENT_LABELS.get(key, key)


def _format_agent_list(keys: list[str]) -> str:
    order = {k: i for i, k in enumerate(_AGENT_DISPLAY_ORDER)}
    ordered = sorted(keys, key=lambda k: order.get(k, 99))
    return ", ".join(_agent_label(k) for k in ordered)


def _theme_rank_score(theme: FinalTheme) -> float:
    return theme.investability_score + theme.consensus_score


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .main-header { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }
        .sub-header { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }
        .summary-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.5rem;
            line-height: 1.7;
        }
        .theme-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
        }
        .stage-badge {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .agent-pill {
            display: inline-block;
            background: #0f172a;
            border: 1px solid #475569;
            border-radius: 6px;
            padding: 0.15rem 0.5rem;
            font-size: 0.75rem;
            margin-right: 0.35rem;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stMetric"] {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _stage_badge(stage_key: str, label: str) -> str:
    fg, bg = STAGE_COLORS.get(stage_key, ("#e2e8f0", "#334155"))
    return (
        f'<span class="stage-badge" style="color:{fg};background:{bg};border:1px solid {fg}40">'
        f"{_esc(label)}</span>"
    )


def _agent_pills(theme: FinalTheme) -> str:
    parts = []
    stages = theme.agent_stages or {}
    contrib = set(theme.contributing_agents or [])
    for key in _AGENT_DISPLAY_ORDER:
        agent = _agent_label(key)
        if key in stages:
            lbl = stage_label(stages[key])
            parts.append(f'<span class="agent-pill">{_esc(agent)}: {_esc(lbl)}</span>')
        elif key in contrib:
            parts.append(
                f'<span class="agent-pill" style="opacity:0.65">{_esc(agent)}: merged</span>'
            )
        else:
            parts.append(
                f'<span class="agent-pill" style="opacity:0.4">{_esc(agent)}: —</span>'
            )
    return "".join(parts)


def _theme_title(theme: FinalTheme) -> str:
    return theme.name


def _theme_subtitle(theme: FinalTheme) -> str:
    sub = (theme.subtitle or "").strip()
    if sub and sub != theme.name:
        return sub
    return ""


def _render_theme_card(rank: int, theme: FinalTheme) -> None:
    stage = coerce_theme_stage(theme.stage)
    stage_key = stage.value
    label = theme.stage_label or stage_label(stage)

    subtitle = _theme_subtitle(theme)
    subtitle_html = (
        f'<span style="color:#64748b;font-size:0.85rem;margin-left:0.5rem;">{_esc(subtitle)}</span>'
        if subtitle
        else ""
    )
    st.html(
        f'<div class="theme-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">'
        f"<div>"
        f'<span style="color:#64748b;font-size:0.85rem;">#{rank}</span>'
        f'<span style="font-size:1.15rem;font-weight:700;margin-left:0.5rem;">'
        f"{_esc(_theme_title(theme))}</span>"
        f"{subtitle_html}"
        f"</div>"
        f"{_stage_badge(stage_key, label)}"
        f"</div>"
        f'<p style="color:#cbd5e1;margin:0.75rem 0 0.5rem;line-height:1.6;">{_esc(theme.thesis)}</p>'
        f'<p style="color:#94a3b8;font-size:0.9rem;margin:0;">{_esc(theme.synthesis)}</p>'
        f'<div style="margin-top:0.75rem;">{_agent_pills(theme)}</div>'
        f"</div>"
    )
    contrib = theme.contributing_agents or []
    if contrib or theme.primary_agent:
        cap = f"Contributors: {_format_agent_list(contrib)}" if contrib else ""
        if theme.primary_agent:
            cap = f"{cap} · Primary: {_agent_label(theme.primary_agent)}".strip(" · ")
        st.caption(cap)

    c1, c2 = st.columns(2)
    with c1:
        st.progress(
            theme.investability_score,
            text=f"Investability {theme.investability_score:.0%}",
        )
    with c2:
        st.progress(theme.consensus_score, text=f"Consensus {theme.consensus_score:.0%}")

    with st.expander("Drivers · Risks · Tickers"):
        if theme.key_drivers:
            st.markdown("**Key drivers** (model synthesis)")
            for d in theme.key_drivers:
                st.markdown(f"- {d}")
        drivers_sourced = theme_drivers_sourced(theme)
        if drivers_sourced:
            st.markdown("**Key drivers (narrative-sourced)**")
            for item in drivers_sourced:
                st.markdown(f"- {item.text} — `{', '.join(item.citation_ids)}`")
        if theme.risks:
            st.markdown("**Risks** (model synthesis)")
            for r in theme.risks:
                st.markdown(f"- {r}")
        risks_sourced = theme_risks_sourced(theme)
        if risks_sourced:
            st.markdown("**Risks (narrative-sourced)**")
            for item in risks_sourced:
                st.markdown(f"- {item.text} — `{', '.join(item.citation_ids)}`")
        if theme.tickers_or_sectors:
            st.markdown("**Tickers / sectors**")
            st.markdown(", ".join(f"`{t}`" for t in theme.tickers_or_sectors))


def _render_agent_theme_column(agent: str, themes: list[AgentTheme]) -> None:
    st.markdown(f"**{_agent_label(agent)}** ({len(themes)} themes)")
    if not themes:
        st.caption("_No themes in this report — re-run analysis._")
        return
    for th in themes:
        stg = stage_label(th.stage)
        st.markdown(f"- **{th.name}** — _{stg}_: {th.thesis[:200]}{'…' if len(th.thesis) > 200 else ''}")


def _brief_date_label(brief: InvestmentBrief) -> str:
    if brief.report_date:
        try:
            return format_date_display(date_cls.fromisoformat(brief.report_date))
        except ValueError:
            pass
    ctx = brief.as_of_context
    if ctx.lower().startswith("as of"):
        return ctx.split("(")[0].replace("As of ", "").strip()
    return format_date_display()


def _render_brief(brief: InvestmentBrief) -> None:
    date_label = _brief_date_label(brief)
    st.markdown(
        '<p class="main-header">📊 Investment Theme Brief</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="sub-header">Analysis date: {date_label}</p>',
        unsafe_allow_html=True,
    )
    if brief.as_of_context:
        st.html(f'<p class="sub-header">{_esc(brief.as_of_context)}</p>')

    st.html(f'<div class="summary-box">{_esc(brief.executive_summary)}</div>')

    st.markdown("### Agent views")
    tab1, tab2, tab3 = st.tabs(
        ["🌍 Regime", "📰 Narrative", "📈 Markets"]
    )
    with tab1:
        st.markdown(brief.regime_view)
    with tab2:
        st.markdown(brief_narrative_view(brief) or "_No narrative view — run a new analysis_")
    with tab3:
        st.markdown("**Fundamentals**")
        st.markdown(brief.markets_fundamentals_view)
        st.markdown("**Volatility**")
        st.markdown(brief.markets_vol_view)
        fund_notes = brief_fundamentals_notes(brief)
        if fund_notes:
            with st.expander("Structured fundamentals (yfinance / Finnhub)"):
                for line in fund_notes:
                    st.markdown(f"- {line}")

    with st.expander("Independent agent themes (before merge)", expanded=False):
        st.caption("Three domain agents — Regime, Narrative, Markets.")
        c1, c2, c3 = st.columns(3)
        with c1:
            _render_agent_theme_column(AGENT_REGIME, brief_agent_themes(brief, AGENT_REGIME))
        with c2:
            _render_agent_theme_column(AGENT_NARRATIVE, brief_agent_themes(brief, AGENT_NARRATIVE))
        with c3:
            _render_agent_theme_column(AGENT_MARKETS, brief_agent_themes(brief, AGENT_MARKETS))

    citations = brief_narrative_citations(brief)
    if citations:
        with st.expander(f"Narrative citations ({len(citations)})"):
            for c in citations:
                st.markdown(f"**[{c.id}]** {c.title} — _{c.source}_")
                if c.url:
                    st.markdown(f"[Link]({c.url})")
                if c.published_at:
                    st.caption(c.published_at)

    sources = brief_data_sources(brief)
    if sources:
        with st.expander("Data sources"):
            for s in sources:
                st.markdown(f"- {s}")

    st.markdown("### Recommended themes")
    st.caption(
        "Sorted by investability + consensus (desc) · One card per sector · "
        "Pills show each agent's stage (— = no matching theme from that agent)"
    )

    sorted_themes = sorted(brief.themes, key=_theme_rank_score, reverse=True)
    stage_counts = {s.value: 0 for s in STAGE_ORDER}
    for t in sorted_themes:
        try:
            key = coerce_theme_stage(t.stage).value
            stage_counts[key] = stage_counts.get(key, 0) + 1
        except ValueError:
            pass

    cols = st.columns(1 + len(STAGE_ORDER))
    cols[0].metric("Themes", len(sorted_themes))
    for i, stage in enumerate(STAGE_ORDER, start=1):
        cols[i].metric(STAGE_LABELS[stage.value], stage_counts.get(stage.value, 0))

    for i, theme in enumerate(sorted_themes, 1):
        _render_theme_card(i, theme)

    st.caption(brief.disclaimer)


def _position_label(p) -> str:
    name = model_name(p)
    if name and name != p.symbol:
        return f"{name} ({p.symbol})"
    return p.symbol


def _render_position_pie(positions, *, cash: float = 0.0) -> None:
    """Pie chart of open positions and optional cash by market value."""
    import altair as alt
    import pandas as pd

    slices: list[dict[str, object]] = []
    for p in positions:
        weight = p.market_value if p.market_value is not None else p.cost_basis
        if weight is None or weight <= 0:
            continue
        slices.append({"label": _position_label(p), "value": float(weight)})

    if cash > 0.01:
        slices.append({"label": "Cash", "value": float(cash)})

    if not slices:
        st.caption("_No position weights to chart._")
        return

    df = pd.DataFrame(slices)
    total = float(df["value"].sum())
    df["pct"] = df["value"] / total * 100

    chart = (
        alt.Chart(df)
        .mark_arc(innerRadius=48)
        .encode(
            theta=alt.Theta("value:Q", stack=True),
            color=alt.Color(
                "label:N",
                legend=alt.Legend(title="Holding", orient="right"),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Holding"),
                alt.Tooltip("value:Q", title="Value ($)", format=",.2f"),
                alt.Tooltip("pct:Q", title="Weight (%)", format=".1f"),
            ],
        )
        .properties(height=340)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, use_container_width=True)


def _render_performance_compare(*, ledger: LedgerKind = "manual") -> None:
    """Line chart: portfolio vs SPY, chain-linked from first investment day in range."""
    import altair as alt
    import pandas as pd

    st.markdown("#### Performance vs S&P 500")
    st.caption(
        f"Chain-linked index (100 = first day with holdings, on or after "
        f"{DEFAULT_COMPARE_START.isoformat()}) · SPY rebased to same start day"
    )

    with st.spinner("Loading performance history…"):
        points = compare_performance_series(from_date=DEFAULT_COMPARE_START, ledger=ledger)

    if not points:
        st.caption("_Benchmark data unavailable._")
        return

    rows: list[dict[str, object]] = []
    for pt in points:
        rows.append(
            {
                "date": pt.date.isoformat(),
                "Index": pt.portfolio_index,
                "Series": "Portfolio",
            }
        )
        rows.append(
            {
                "date": pt.date.isoformat(),
                "Index": pt.spy_index,
                "Series": "S&P 500 (SPY)",
            }
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    chart = (
        alt.Chart(df)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("Index:Q", title="Index (100 = start)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=["Portfolio", "S&P 500 (SPY)"],
                    range=["#38bdf8", "#fbbf24"],
                ),
                legend=alt.Legend(title=""),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("Series:N", title=""),
                alt.Tooltip("Index:Q", title="Index", format=".2f"),
            ],
        )
        .properties(height=360)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, use_container_width=True)

    last = points[-1]
    port_ret = last.portfolio_index - 100.0
    spy_ret = last.spy_index - 100.0
    st.caption(
        f"Indexed return since portfolio start · Portfolio **{port_ret:+.1f}%** · "
        f"SPY **{spy_ret:+.1f}%** · "
        f"Spread **{port_ret - spy_ret:+.1f} pp**"
    )


def _render_theme_alignment(brief: InvestmentBrief, snapshot) -> None:
    """Research themes vs holdings (read-only overlay)."""
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


def _render_portfolio_compare(brief: InvestmentBrief | None) -> None:
    """Manual holdings vs brief target weights (read-only; requires allocation MVP)."""
    st.markdown("#### Compare — manual vs research target")
    st.caption(
        "Your real portfolio vs target weights from the theme brief. "
        "Read-only — does not record trades."
    )
    if brief is None:
        st.info(
            "Load a theme brief (**Themes** → **Load last result** or run analysis) "
            "to compare holdings against research targets."
        )
        return
    try:
        summary = summarize_performance(ledger="manual")
    except RuntimeError as e:
        st.error(f"Database error: {e}")
        return
    if summary.first_trade_date is None:
        st.info("No manual trades yet. Record trades under **My portfolio** first.")
        return
    try:
        from investment_agent.portfolio.allocation import compute_target_allocation
        from investment_agent.portfolio.drift import compute_drift_report
    except ImportError:
        st.info(
            "Target allocation and drift modules are not installed yet. "
            "Use **My portfolio** → Research alignment for theme overlap until the "
            "allocation MVP ships."
        )
        return
    target = compute_target_allocation(brief)
    report = compute_drift_report(summary.snapshot, target)
    if not report.rows:
        st.caption("_No drift rows._")
        return
    table_rows = [
        {
            "Symbol": row.symbol,
            "Target %": f"{row.target_pct:.1f}",
            "Actual %": f"{row.actual_pct:.1f}",
            "Drift (pp)": f"{row.drift_pp:+.1f}",
            "Severity": row.severity,
        }
        for row in report.rows
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def _render_portfolio_ledger(
    brief: InvestmentBrief | None,
    ledger: LedgerKind,
    *,
    show_theme_alignment: bool,
) -> None:
    is_model = ledger == "model"
    ledger_label = "Paper / model ledger" if is_model else "My portfolio (manual)"
    st.markdown(f"##### {ledger_label}")
    db_file = portfolio_db.db_path(ledger)
    st.caption(f"Ledger: `{db_file}`")

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

    _render_performance_compare(ledger=ledger)

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
            _render_position_pie(
                summary.snapshot.positions,
                cash=cash_bal,
            )
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


def _render_portfolio(brief: InvestmentBrief | None = None) -> None:
    st.markdown(
        '<p class="main-header">💼 Portfolio</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sub-header">Manual vs model ledgers · performance vs SPY</p>',
        unsafe_allow_html=True,
    )

    view = st.radio(
        "Portfolio view",
        ["My portfolio", "Model portfolio", "Compare"],
        horizontal=True,
        key="portfolio_sub_view",
    )

    if view == "Compare":
        _render_portfolio_compare(brief)
        return

    ledger: LedgerKind = "manual" if view == "My portfolio" else "model"
    _render_portfolio_ledger(
        brief,
        ledger,
        show_theme_alignment=(ledger == "manual"),
    )


def main() -> None:
    _inject_css()

    if "brief" not in st.session_state:
        st.session_state.brief = load_brief()

    with st.sidebar:
        st.header("Controls")
        page = st.radio("View", ["Themes", "Portfolio"], index=0, horizontal=True)
        st.divider()
        region = st.selectbox(
            "Market region",
            ["global", "China", "US", "Europe", "Japan"],
            index=0,
        )
        st.divider()
        run_btn = st.button("🚀 Run analysis", type="primary", use_container_width=True)
        st.caption("Takes 2–4 min (~3 LLM calls). Regime · Narrative · Markets.")
        resume_ckpt = st.checkbox(
            "Resume from checkpoint (skip completed agents)",
            value=checkpoint.is_resume_enabled(),
            help="Saves progress under reports/cache/. After a 429 error, rerun to continue.",
        )
        cached_steps = checkpoint.list_checkpoint_steps()
        if cached_steps:
            st.caption(f"Checkpoint: {', '.join(cached_steps)}")
            if st.button("Clear checkpoint", use_container_width=True):
                checkpoint.clear_checkpoint()
                st.rerun()
        if DEFAULT_REPORT_PATH.is_file():
            st.success("Cached report available")
            if st.button("📂 Load last result", use_container_width=True):
                loaded = load_brief()
                if loaded is not None:
                    st.session_state.brief = loaded
                st.rerun()
        st.divider()
        try:
            s = Settings.from_env()
            st.text(f"Model: {s.provider}\n{s.model}")
        except ValueError as e:
            st.error(str(e))

    if run_btn:
        try:
            settings = Settings.from_env()
            from dataclasses import replace

            settings = replace(settings, market_region=region)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        with st.status("Running 3-agent analysis…", expanded=True) as status:
            st.write("Regime agent")
            st.write("Narrative agent (news RAG)")
            st.write("Markets agent (fundamentals + vol)")
            st.write("Brief assembler (programmatic merge)")
            try:
                brief = ThemeOrchestrator(settings).run(resume=resume_ckpt)
                latest_path, archive_path = save_run_reports(brief)
                st.session_state.brief = brief
                status.update(label="Analysis complete", state="complete")
                st.success(f"Saved to `{latest_path}` · archive `{archive_path}`")
            except QuotaExhaustedError as e:
                status.update(label="API quota exceeded", state="error")
                st.error(e.user_hint())
                steps = checkpoint.list_checkpoint_steps()
                if steps:
                    st.info(
                        f"Progress saved: **{', '.join(steps)}**. "
                        "Keep **Resume from checkpoint** on and run again later."
                    )
                st.stop()
            except Exception as e:
                status.update(label="Analysis failed", state="error")
                st.error(f"Run failed: {e}")
                steps = checkpoint.list_checkpoint_steps()
                if steps:
                    st.warning(
                        f"Partial progress saved ({', '.join(steps)}). "
                        "Enable resume and retry."
                    )
                st.stop()

    if page == "Portfolio":
        _render_portfolio(brief=st.session_state.get("brief"))
        return

    brief: InvestmentBrief | None = st.session_state.get("brief")

    if brief is None:
        st.info("👈 Click **Run analysis** in the sidebar, or **Load last result** to view cache.")
        return

    _render_brief(brief)

    with st.expander("Raw JSON"):
        st.json(brief.model_dump(mode="json", by_alias=True))


if __name__ == "__main__":
    main()
