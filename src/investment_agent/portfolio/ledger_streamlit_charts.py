"""Streamlit charts shared by manual and model portfolio views."""

from __future__ import annotations

import streamlit as st

from investment_agent.portfolio.db import LedgerKind
from investment_agent.portfolio.models import model_name
from investment_agent.portfolio.performance import (
    DEFAULT_COMPARE_START,
    compare_performance_series,
)


def _position_label(p) -> str:
    name = model_name(p)
    if name and name != p.symbol:
        return f"{name} ({p.symbol})"
    return p.symbol


def render_position_pie(positions, *, cash: float = 0.0) -> None:
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


def render_performance_compare(
    *,
    ledger: LedgerKind = "manual",
    path=None,
) -> None:
    """Line chart: portfolio vs SPY, chain-linked from first investment day in range."""
    st.markdown("#### Performance vs S&P 500")
    st.caption(
        f"Chain-linked index (100 = first day with holdings, on or after "
        f"{DEFAULT_COMPARE_START.isoformat()}) · SPY rebased to same start day"
    )

    with st.spinner("Loading performance history…"):
        points = compare_performance_series(
            from_date=DEFAULT_COMPARE_START,
            ledger=ledger,
            path=path,
        )

    if not points:
        st.caption("_Benchmark data unavailable._")
        return

    _render_index_chart(
        [("Portfolio", points)],
        spy_from=points,
    )


def render_model_target_performance(
    target_points: list,
    *,
    ledger_points: list | None = None,
    as_of_label: str,
) -> None:
    """Performance chart for score-weighted model target (optional paper ledger overlay)."""
    if not target_points:
        st.caption("_Benchmark or price data unavailable for target symbols._")
        return

    st.markdown("#### Performance vs S&P 500")
    st.caption(
        f"Model portfolio: buy-and-hold at score-weighted sector ETF targets from {as_of_label} · "
        "SPY rebased to the same start day · no single stocks"
    )

    series: list[tuple[str, list]] = [("Model (target)", target_points)]
    if ledger_points:
        series.append(("Model (paper ledger)", ledger_points))

    with st.spinner("Loading performance history…"):
        _render_index_chart(series, spy_from=target_points)


def _render_index_chart(
    series: list[tuple[str, list]],
    *,
    spy_from: list,
) -> None:
    import altair as alt
    import pandas as pd

    rows: list[dict[str, object]] = []
    for name, points in series:
        for pt in points:
            rows.append(
                {
                    "date": pt.date.isoformat(),
                    "Index": pt.portfolio_index,
                    "Series": name,
                }
            )
    for pt in spy_from:
        rows.append(
            {
                "date": pt.date.isoformat(),
                "Index": pt.spy_index,
                "Series": "S&P 500 (SPY)",
            }
        )

    if not rows:
        st.caption("_No performance data._")
        return

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    color_domain = [name for name, _ in series] + ["S&P 500 (SPY)"]
    palette = ["#38bdf8", "#a78bfa", "#fbbf24"]
    colors = palette[: len(color_domain)]

    chart = (
        alt.Chart(df)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("Index:Q", title="Index (100 = start)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(domain=color_domain, range=colors),
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

    last_target = series[0][1][-1]
    port_ret = last_target.portfolio_index - 100.0
    spy_ret = last_target.spy_index - 100.0
    caption = (
        f"Indexed return since start · Model (target) **{port_ret:+.1f}%** · "
        f"SPY **{spy_ret:+.1f}%** · Spread **{port_ret - spy_ret:+.1f} pp**"
    )
    if len(series) > 1 and series[1][1]:
        ledger_ret = series[1][1][-1].portfolio_index - 100.0
        caption += f" · Paper ledger **{ledger_ret:+.1f}%**"
    st.caption(caption)
