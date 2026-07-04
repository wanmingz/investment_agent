"""Tests for report persistence."""

from datetime import datetime

from investment_agent.models import InvestmentBrief, ThemeStage
from investment_agent.models import FinalTheme
from investment_agent.storage import list_run_reports, run_archive_path, save_run_reports


def _minimal_brief(*, report_date: str = "2026-07-04") -> InvestmentBrief:
    theme = FinalTheme(
        name="Tech",
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=0.5,
        investability_score=0.5,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=[],
    )
    return InvestmentBrief(
        report_date=report_date,
        as_of_context=f"As of {report_date}",
        executive_summary="x",
        regime_view="r",
        themes=[theme],
    )


def test_run_archive_path_uses_report_date_and_time(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "investment_agent.storage.RUNS_DIR",
        tmp_path / "runs",
    )
    brief = _minimal_brief()
    path = run_archive_path(brief, now=datetime(2026, 7, 4, 12, 30, 45))
    assert path.name == "2026-07-04_123045.json"


def test_save_run_reports_writes_latest_and_archive(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    monkeypatch.setattr("investment_agent.storage.DEFAULT_REPORT_PATH", reports / "latest.json")
    monkeypatch.setattr("investment_agent.storage.RUNS_DIR", reports / "runs")

    brief = _minimal_brief()
    fixed = datetime(2026, 7, 4, 9, 15, 0)
    monkeypatch.setattr(
        "investment_agent.storage.run_archive_path",
        lambda b, now=None: reports / "runs" / "2026-07-04_091500.json",
    )

    latest, archive = save_run_reports(brief)
    assert latest == reports / "latest.json"
    assert archive == reports / "runs" / "2026-07-04_091500.json"
    assert latest.is_file()
    assert archive.is_file()
    assert list_run_reports(limit=5) == [archive]
