"""Tests for Markdown report rendering."""

from datetime import datetime

from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.report_markdown import (
    format_brief_markdown,
    markdown_archive_path,
    save_github_brief_reports,
)


def _minimal_brief() -> InvestmentBrief:
    theme = FinalTheme(
        name="AI Infrastructure",
        thesis="Hyperscaler capex supports the theme.",
        stage=ThemeStage.MID,
        stage_label="Mid",
        consensus_score=0.75,
        investability_score=0.6,
        synthesis="Earnings and flows confirm the trend.",
        key_drivers=["Capex cycle"],
        risks=["Valuation"],
        tickers_or_sectors=["NVDA", "Semiconductors"],
        agent_stages={"regime": ThemeStage.MID, "narrative": ThemeStage.EARLY_MID},
        contributing_agents=["regime", "narrative"],
        primary_agent="regime",
    )
    return InvestmentBrief(
        report_date="2026-07-07",
        as_of_context="As of 2026-07-07 · US session",
        executive_summary="Risk-on backdrop with selective tech leadership.",
        regime_view="Global growth stabilizing.",
        narrative_view="Headlines favor AI and power demand.",
        markets_fundamentals_view="Earnings revisions positive in tech.",
        markets_vol_view="VIX subdued.",
        themes=[theme],
    )


def test_format_brief_markdown_includes_core_sections() -> None:
    md = format_brief_markdown(_minimal_brief())
    assert "# Investment Theme Brief" in md
    assert "AI Infrastructure" in md
    assert "## Recommended themes" in md
    assert "NVDA" in md
    assert "Risk-on backdrop" in md


def test_markdown_archive_path_uses_timestamp() -> None:
    brief = _minimal_brief()
    path = markdown_archive_path(brief, now=datetime(2026, 7, 7, 6, 0, 0))
    assert path.name == "2026-07-07_060000.md"


def test_save_github_brief_reports_writes_latest_and_archive(tmp_path) -> None:
    base = tmp_path / "brief"
    latest, archive = save_github_brief_reports(
        _minimal_brief(),
        base_dir=base,
        now=datetime(2026, 7, 7, 6, 0, 0),
    )
    assert latest == base / "latest.md"
    assert archive == base / "runs" / "2026-07-07_060000.md"
    assert "AI Infrastructure" in latest.read_text(encoding="utf-8")
    published = base / "latest.json"
    assert published.is_file()
    assert "AI Infrastructure" in published.read_text(encoding="utf-8")
