"""Investment theme dashboard — run: streamlit run streamlit_app.py"""

from __future__ import annotations

import sys
from datetime import date as date_cls
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from investment_agent.brief_compat import (
    brief_data_sources,
    brief_news_citations,
    brief_news_view,
    theme_drivers_sourced,
    theme_risks_sourced,
)
from investment_agent.config import Settings
from investment_agent.dates import analysis_date, format_date_iso
from investment_agent.models import (
    STAGE_LABELS,
    STAGE_ORDER,
    FinalTheme,
    InvestmentBrief,
    coerce_theme_stage,
    stage_label,
)
from investment_agent.orchestrator import ThemeOrchestrator
from investment_agent.storage import DEFAULT_REPORT_PATH, load_brief, save_brief

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

AGENT_LABELS = {
    "macro": "Macro",
    "news": "News",
    "equity": "Equity",
    "quant": "Quant",
}


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


def _stage_badge(stage_key: str, label: str) -> str:
    fg, bg = STAGE_COLORS.get(stage_key, ("#e2e8f0", "#334155"))
    return (
        f'<span class="stage-badge" style="color:{fg};background:{bg};border:1px solid {fg}40">'
        f"{label}</span>"
    )


def _agent_pills(theme: FinalTheme) -> str:
    parts = []
    for key, stg in theme.agent_stages.items():
        agent = AGENT_LABELS.get(key, key)
        lbl = stage_label(stg)
        parts.append(f'<span class="agent-pill">{agent}: {lbl}</span>')
    return "".join(parts)


def _theme_title(theme: FinalTheme) -> str:
    return theme.subtitle or theme.name


def _render_theme_card(rank: int, theme: FinalTheme) -> None:
    stage = coerce_theme_stage(theme.stage)
    stage_key = stage.value
    label = theme.stage_label or stage_label(stage)

    st.markdown(
        f"""
        <div class="theme-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">
                <div>
                    <span style="color:#64748b;font-size:0.85rem;">#{rank}</span>
                    <span style="font-size:1.15rem;font-weight:700;margin-left:0.5rem;">
                        {_theme_title(theme)}
                    </span>
                    <span style="color:#64748b;font-size:0.85rem;margin-left:0.5rem;">{theme.name}</span>
                </div>
                {_stage_badge(stage_key, label)}
            </div>
            <p style="color:#cbd5e1;margin:0.75rem 0 0.5rem;line-height:1.6;">{theme.thesis}</p>
            <p style="color:#94a3b8;font-size:0.9rem;margin:0;">{theme.synthesis}</p>
            <div style="margin-top:0.75rem;">{_agent_pills(theme)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            st.markdown("**Key drivers (news-sourced)**")
            for item in drivers_sourced:
                st.markdown(f"- {item.text} — `{', '.join(item.citation_ids)}`")
        if theme.risks:
            st.markdown("**Risks** (model synthesis)")
            for r in theme.risks:
                st.markdown(f"- {r}")
        risks_sourced = theme_risks_sourced(theme)
        if risks_sourced:
            st.markdown("**Risks (news-sourced)**")
            for item in risks_sourced:
                st.markdown(f"- {item.text} — `{', '.join(item.citation_ids)}`")
        if theme.tickers_or_sectors:
            st.markdown("**Tickers / sectors**")
            st.markdown(", ".join(f"`{t}`" for t in theme.tickers_or_sectors))


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
        st.markdown(f'<p class="sub-header">{brief.as_of_context}</p>', unsafe_allow_html=True)

    st.markdown(f'<div class="summary-box">{brief.executive_summary}</div>', unsafe_allow_html=True)

    st.markdown("### Agent views")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🌍 Macro", "📰 News RAG", "📈 Equity", "📉 Quant"]
    )
    with tab1:
        st.markdown(brief.macro_view)
    with tab2:
        st.markdown(brief_news_view(brief) or "_No news view — run a new analysis with News RAG_")
    with tab3:
        st.markdown(brief.equity_view)
    with tab4:
        st.markdown(brief.quant_view)

    citations = brief_news_citations(brief)
    if citations:
        with st.expander(f"News citations ({len(citations)})"):
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
        "Sorted by investability · Early → Early-Mid → Mid → Mid-Late → Late (5-stage lifecycle)"
    )

    sorted_themes = sorted(brief.themes, key=lambda t: t.investability_score, reverse=True)
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


def main() -> None:
    _inject_css()

    if "brief" not in st.session_state:
        st.session_state.brief = load_brief()

    with st.sidebar:
        st.header("Controls")
        region = st.selectbox(
            "Market region",
            ["global", "China", "US", "Europe", "Japan"],
            index=0,
        )
        st.divider()
        run_btn = st.button("🚀 Run analysis", type="primary", use_container_width=True)
        st.caption("Takes 2–4 min (4 agents + news RAG + CIO)")
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

        with st.status("Running 4-agent analysis…", expanded=True) as status:
            st.write("Agent 1: Macro Economist")
            st.write("Agent 2: News / RAG (Finnhub + TickerTick)")
            st.write("Agent 3: Equity Research Analyst")
            st.write("Agent 4: Quant / Volatility Analyst")
            st.write("CIO: Synthesizing investment brief")
            try:
                brief = ThemeOrchestrator(settings).run()
                path = save_brief(brief)
                st.session_state.brief = brief
                status.update(label="Analysis complete", state="complete")
                st.success(f"Saved to `{path}`")
            except Exception as e:
                status.update(label="Analysis failed", state="error")
                st.error(f"Run failed: {e}")
                st.stop()

    brief: InvestmentBrief | None = st.session_state.get("brief")

    if brief is None:
        st.info("👈 Click **Run analysis** in the sidebar, or **Load last result** to view cache.")
        return

    _render_brief(brief)

    with st.expander("Raw JSON"):
        st.json(brief.model_dump(mode="json", by_alias=True))


if __name__ == "__main__":
    main()
