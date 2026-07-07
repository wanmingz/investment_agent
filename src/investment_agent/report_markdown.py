"""Render InvestmentBrief as GitHub-friendly Markdown."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from investment_agent.models import (
    AGENT_LABELS,
    AGENT_REGIME,
    AGENT_NARRATIVE,
    AGENT_MARKETS,
    FinalTheme,
    InvestmentBrief,
    ThemeStage,
    coerce_theme_stage,
    stage_label,
    theme_rank_score,
)
from investment_agent.storage import (
    brief_agent_themes,
    brief_data_sources,
    brief_fundamentals_notes,
    brief_narrative_citations,
    brief_narrative_view,
    theme_drivers_sourced,
    theme_risks_sourced,
)

BRIEF_DIR = Path(__file__).resolve().parents[2] / "brief"
BRIEF_LATEST = BRIEF_DIR / "latest.md"
BRIEF_RUNS_DIR = BRIEF_DIR / "runs"


def _md_line(text: str) -> str:
    """Escape characters that would break Markdown structure."""
    if not text:
        return ""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("#", ">", "|", "-", "*", "+")):
            line = "\\" + line.lstrip()
        out.append(line)
    return "\n".join(out)


def _md_inline(text: str) -> str:
    return _md_line(text).replace("|", "\\|")


def _brief_title_line(brief: InvestmentBrief) -> str:
    if brief.report_date:
        return f"As of {brief.report_date}"
    ctx = brief.as_of_context.strip()
    if ctx.lower().startswith("as of"):
        return ctx.split("·")[0].strip()
    return "Investment theme brief"


def _agent_stage_pills(theme: FinalTheme) -> str:
    parts: list[str] = []
    for agent in (AGENT_REGIME, AGENT_NARRATIVE, AGENT_MARKETS):
        label = AGENT_LABELS.get(agent, agent)
        stage = theme.agent_stages.get(agent)
        if stage is None:
            parts.append(f"{label}: —")
        else:
            parts.append(f"{label}: {stage_label(stage)}")
    return " · ".join(parts)


def _format_theme_section(rank: int, theme: FinalTheme) -> list[str]:
    stage = coerce_theme_stage(theme.stage)
    label = theme.stage_label or stage_label(stage)
    score = theme_rank_score(theme)
    lines = [
        f"### {rank}. {theme.name}",
        "",
        f"**Stage:** {label} · **Investability:** {theme.investability_score:.0%} · "
        f"**Consensus:** {theme.consensus_score:.0%} · **Score:** {score:.2f}",
        "",
        f"**Agent stages:** {_agent_stage_pills(theme)}",
        "",
    ]
    if theme.contributing_agents or theme.primary_agent:
        contrib = ", ".join(AGENT_LABELS.get(a, a) for a in theme.contributing_agents)
        primary = AGENT_LABELS.get(theme.primary_agent, theme.primary_agent)
        meta: list[str] = []
        if contrib:
            meta.append(f"Contributors: {contrib}")
        if theme.primary_agent:
            meta.append(f"Primary: {primary}")
        lines.append(" · ".join(meta))
        lines.append("")

    lines.extend([_md_line(theme.thesis), "", f"_{_md_line(theme.synthesis)}_", ""])

    if theme.key_drivers:
        lines.append("**Key drivers**")
        lines.extend(f"- {_md_inline(d)}" for d in theme.key_drivers)
        lines.append("")

    drivers_sourced = theme_drivers_sourced(theme)
    if drivers_sourced:
        lines.append("**Key drivers (narrative-sourced)**")
        for item in drivers_sourced:
            refs = ", ".join(item.citation_ids)
            lines.append(f"- {_md_inline(item.text)} (`{refs}`)")
        lines.append("")

    if theme.risks:
        lines.append("**Risks**")
        lines.extend(f"- {_md_inline(r)}" for r in theme.risks)
        lines.append("")

    risks_sourced = theme_risks_sourced(theme)
    if risks_sourced:
        lines.append("**Risks (narrative-sourced)**")
        for item in risks_sourced:
            refs = ", ".join(item.citation_ids)
            lines.append(f"- {_md_inline(item.text)} (`{refs}`)")
        lines.append("")

    if theme.tickers_or_sectors:
        tickers = ", ".join(f"`{t}`" for t in theme.tickers_or_sectors)
        lines.append(f"**Tickers / sectors:** {tickers}")
        lines.append("")

    return lines


def _format_agent_themes_block(brief: InvestmentBrief) -> list[str]:
    lines = ["## Agent themes (pre-merge)", ""]
    for agent in (AGENT_REGIME, AGENT_NARRATIVE, AGENT_MARKETS):
        themes = brief_agent_themes(brief, agent)
        label = AGENT_LABELS.get(agent, agent)
        lines.append(f"### {label} ({len(themes)})")
        if not themes:
            lines.append("")
            lines.append("_No themes in this report._")
            lines.append("")
            continue
        for th in themes:
            stg = stage_label(th.stage)
            thesis = th.thesis[:200] + ("…" if len(th.thesis) > 200 else "")
            lines.append(f"- **{th.name}** — _{stg}_: {_md_inline(thesis)}")
        lines.append("")
    return lines


def format_brief_markdown(brief: InvestmentBrief) -> str:
    """Full Markdown document for GitHub rendering."""
    title = _brief_title_line(brief)
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "# Investment Theme Brief",
        "",
        f"**{title}**",
        "",
    ]
    if brief.as_of_context and brief.as_of_context != title:
        lines.extend([_md_line(brief.as_of_context), ""])

    lines.extend(
        [
            f"> {_md_line(brief.executive_summary)}",
            "",
            f"_Generated {generated} by investment-agent CI._",
            "",
            "---",
            "",
            "## Agent views",
            "",
            "### Regime",
            "",
            _md_line(brief.regime_view) or "_—_",
            "",
            "### Narrative",
            "",
            _md_line(brief_narrative_view(brief)) or "_—_",
            "",
            "### Markets — fundamentals",
            "",
            _md_line(brief.markets_fundamentals_view) or "_—_",
            "",
            "### Markets — volatility",
            "",
            _md_line(brief.markets_vol_view) or "_—_",
            "",
        ]
    )

    fund_notes = brief_fundamentals_notes(brief)
    if fund_notes:
        lines.extend(["<details>", "<summary>Structured fundamentals (yfinance / Finnhub)</summary>", ""])
        lines.extend(f"- {_md_inline(n)}" for n in fund_notes)
        lines.extend(["", "</details>", ""])

    lines.extend(_format_agent_themes_block(brief))

    citations = brief_narrative_citations(brief)
    if citations:
        lines.extend(["<details>", f"<summary>Narrative citations ({len(citations)})</summary>", ""])
        for c in citations:
            link = f" — [link]({c.url})" if c.url else ""
            pub = f" ({c.published_at})" if c.published_at else ""
            lines.append(f"- **[{c.id}]** {_md_inline(c.title)} — _{c.source}_{pub}{link}")
        lines.extend(["", "</details>", ""])

    sources = brief_data_sources(brief)
    if sources:
        lines.extend(["<details>", "<summary>Data sources</summary>", ""])
        lines.extend(f"- {_md_inline(s)}" for s in sources)
        lines.extend(["", "</details>", ""])

    sorted_themes = sorted(brief.themes, key=theme_rank_score, reverse=True)
    stage_counts = {s.value: 0 for s in ThemeStage}
    for t in sorted_themes:
        try:
            stage_counts[coerce_theme_stage(t.stage).value] += 1
        except ValueError:
            pass

    lines.extend(
        [
            "## Recommended themes",
            "",
            f"_{len(sorted_themes)} themes · sorted by investability + consensus_",
            "",
            "| Stage | Count |",
            "|-------|------:|",
        ]
    )
    for stage in ThemeStage:
        lines.append(f"| {stage_label(stage)} | {stage_counts.get(stage.value, 0)} |")
    lines.append("")

    for i, theme in enumerate(sorted_themes, 1):
        lines.extend(_format_theme_section(i, theme))

    lines.extend(["---", "", f"_{brief.disclaimer}_", ""])
    return "\n".join(lines)


def markdown_archive_path(
    brief: InvestmentBrief,
    *,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    base = base_dir or BRIEF_DIR
    now = now or datetime.now()
    date_part = brief.report_date or now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%S")
    return base / "runs" / f"{date_part}_{stamp}.md"


def save_brief_markdown(brief: InvestmentBrief, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_brief_markdown(brief), encoding="utf-8")
    return path


def save_github_brief_reports(
    brief: InvestmentBrief,
    *,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """Write brief/latest.md and a timestamped brief/runs/*.md copy."""
    base = base_dir or BRIEF_DIR
    latest = save_brief_markdown(brief, base / "latest.md")
    archive = save_brief_markdown(brief, markdown_archive_path(brief, base_dir=base, now=now))
    return latest, archive
