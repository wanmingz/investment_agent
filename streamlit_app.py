"""Investment theme dashboard — run: streamlit run streamlit_app.py"""

from __future__ import annotations

import streamlit as st

from investment_agent.config import Settings
from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.orchestrator import STAGE_ZH, ThemeOrchestrator
from investment_agent.storage import DEFAULT_REPORT_PATH, load_brief, save_brief

st.set_page_config(
    page_title="投资主题分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

STAGE_COLORS = {
    ThemeStage.EARLY: ("#10b981", "#064e3b"),
    ThemeStage.MID: ("#f59e0b", "#78350f"),
    ThemeStage.LATE: ("#ef4444", "#7f1d1d"),
}

AGENT_LABELS = {
    "macro": "宏观",
    "equity": "股票",
    "quant": "量化",
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


def _stage_badge(stage: ThemeStage, label: str) -> str:
    fg, bg = STAGE_COLORS.get(stage, ("#e2e8f0", "#334155"))
    return (
        f'<span class="stage-badge" style="color:{fg};background:{bg};border:1px solid {fg}40">'
        f"{label}</span>"
    )


def _agent_pills(theme: FinalTheme) -> str:
    parts = []
    for key, stage in theme.agent_stages.items():
        label = AGENT_LABELS.get(key, key)
        stage_zh = STAGE_ZH.get(stage, stage.value if hasattr(stage, "value") else str(stage))
        parts.append(f'<span class="agent-pill">{label}: {stage_zh}</span>')
    return "".join(parts)


def _render_theme_card(rank: int, theme: FinalTheme) -> None:
    stage = theme.stage if isinstance(theme.stage, ThemeStage) else ThemeStage(theme.stage)
    label = theme.stage_label_zh or STAGE_ZH.get(stage, stage.value)

    st.markdown(
        f"""
        <div class="theme-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">
                <div>
                    <span style="color:#64748b;font-size:0.85rem;">#{rank}</span>
                    <span style="font-size:1.15rem;font-weight:700;margin-left:0.5rem;">
                        {theme.name_zh or theme.name}
                    </span>
                    <span style="color:#64748b;font-size:0.85rem;margin-left:0.5rem;">{theme.name}</span>
                </div>
                {_stage_badge(stage, label)}
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
            text=f"可投资性 {theme.investability_score:.0%}",
        )
    with c2:
        st.progress(theme.consensus_score, text=f"共识度 {theme.consensus_score:.0%}")

    with st.expander("驱动因素 · 风险 · 标的"):
        if theme.key_drivers:
            st.markdown("**驱动因素**")
            for d in theme.key_drivers:
                st.markdown(f"- {d}")
        if theme.risks:
            st.markdown("**风险**")
            for r in theme.risks:
                st.markdown(f"- {r}")
        if theme.tickers_or_sectors:
            st.markdown("**标的 / 板块**")
            st.markdown(", ".join(f"`{t}`" for t in theme.tickers_or_sectors))


def _render_brief(brief: InvestmentBrief) -> None:
    st.markdown('<p class="main-header">📊 投资主题简报</p>', unsafe_allow_html=True)
    if brief.as_of_context:
        st.markdown(f'<p class="sub-header">{brief.as_of_context}</p>', unsafe_allow_html=True)

    st.markdown(f'<div class="summary-box">{brief.executive_summary}</div>', unsafe_allow_html=True)

    st.markdown("### 三 Agent 观点")
    tab1, tab2, tab3 = st.tabs(["🌍 宏观经济学家", "📈 股票研究员", "📉 量化波动"])
    with tab1:
        st.markdown(brief.macro_view)
    with tab2:
        st.markdown(brief.equity_view)
    with tab3:
        st.markdown(brief.quant_view)

    st.markdown("### 推荐投资主题")
    st.caption("按可投资性排序 · 早期=布局期 · 中期=主升期 · 晚期=过热观察")

    sorted_themes = sorted(brief.themes, key=lambda t: t.investability_score, reverse=True)
    early = sum(1 for t in sorted_themes if t.stage == ThemeStage.EARLY)
    mid = sum(1 for t in sorted_themes if t.stage == ThemeStage.MID)
    late = sum(1 for t in sorted_themes if t.stage == ThemeStage.LATE)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("主题数", len(sorted_themes))
    m2.metric("早期", early)
    m3.metric("中期", mid)
    m4.metric("晚期", late)

    for i, theme in enumerate(sorted_themes, 1):
        _render_theme_card(i, theme)

    st.caption(brief.disclaimer)


def main() -> None:
    _inject_css()

    if "brief" not in st.session_state:
        st.session_state.brief = load_brief()

    with st.sidebar:
        st.header("控制面板")
        region = st.selectbox(
            "市场区域",
            ["global", "China", "US", "Europe", "Japan"],
            index=0,
        )
        st.divider()
        run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
        st.caption("分析需 1–3 分钟（3 个 Agent + CIO 合成）")
        if DEFAULT_REPORT_PATH.is_file():
            st.success("已有缓存报告")
            if st.button("📂 加载上次结果", use_container_width=True):
                st.session_state.brief = load_brief()
                st.rerun()
        st.divider()
        try:
            s = Settings.from_env()
            st.text(f"模型: {s.provider}\n{s.model}")
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

        with st.status("正在运行三 Agent 分析…", expanded=True) as status:
            st.write("Agent 1: 宏观经济学家")
            st.write("Agent 2: 股票研究员")
            st.write("Agent 3: 量化波动分析师")
            st.write("CIO: 合成投资简报")
            try:
                brief = ThemeOrchestrator(settings).run()
                path = save_brief(brief)
                st.session_state.brief = brief
                status.update(label="分析完成", state="complete")
                st.success(f"结果已保存至 `{path}`")
            except Exception as e:
                status.update(label="分析失败", state="error")
                st.error(f"运行失败: {e}")
                st.stop()

    brief: InvestmentBrief | None = st.session_state.get("brief")

    if brief is None:
        st.info("👈 点击侧边栏 **「开始分析」** 运行，或 **「加载上次结果」** 查看缓存。")
        st.markdown(
            """
            **也可通过命令行生成报告后在此查看：**
            ```bash
            python main.py --json > reports/latest.json
            ```
            然后点击「加载上次结果」。
            """
        )
        return

    _render_brief(brief)

    with st.expander("原始 JSON"):
        st.json(brief.model_dump(mode="json"))


if __name__ == "__main__":
    main()
