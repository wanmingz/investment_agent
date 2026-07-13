"""Tests for score-weighted target allocation."""

from __future__ import annotations

from datetime import date

from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.portfolio.compare.allocation import compute_target_allocation


def _theme(name: str, tickers: list[str], score: float = 1.0) -> FinalTheme:
    half = score / 2
    return FinalTheme(
        name=name,
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=half,
        investability_score=half,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=tickers,
    )


def _brief(*themes: FinalTheme) -> InvestmentBrief:
    return InvestmentBrief(
        report_date="2026-07-01",
        as_of_context="As of 2026-07-01",
        executive_summary="x",
        regime_view="r",
        themes=list(themes),
    )


def test_theme_weights_proportional_to_rank_score() -> None:
    brief = _brief(
        _theme("A", ["AAPL"], score=1.6),
        _theme("B", ["MSFT"], score=0.8),
    )
    target = compute_target_allocation(brief, top_n=8)
    by_sym = {r.symbol: r.target_pct for r in target.rows}
    assert by_sym["AAPL"] == 66.66666666666666
    assert by_sym["MSFT"] == 33.33333333333333
    assert abs(target.total_target_pct - 100.0) < 1e-6


def test_equal_split_within_theme() -> None:
    brief = _brief(_theme("Tech", ["AAPL", "NVDA"], score=2.0))
    target = compute_target_allocation(brief)
    by_sym = {r.symbol: r.target_pct for r in target.rows}
    assert by_sym["AAPL"] == 50.0
    assert by_sym["NVDA"] == 50.0


def test_duplicate_ticker_across_themes_sums_then_renormalizes() -> None:
    brief = _brief(
        _theme("T1", ["AAPL", "MSFT"], score=1.0),
        _theme("T2", ["AAPL"], score=1.0),
    )
    target = compute_target_allocation(brief)
    by_sym = {r.symbol: r.target_pct for r in target.rows}
    # T1: AAPL 25%, MSFT 25%; T2: AAPL 50% -> raw AAPL 75%, MSFT 25%
    assert by_sym["AAPL"] == 75.0
    assert by_sym["MSFT"] == 25.0


def test_skips_themes_without_tickers() -> None:
    brief = _brief(
        _theme("Empty", [], score=2.0),
        _theme("Has", ["GOOG"], score=1.0),
    )
    target = compute_target_allocation(brief)
    assert [r.symbol for r in target.rows] == ["GOOG"]
    assert target.rows[0].target_pct == 100.0


def test_top_n_limits_themes() -> None:
    tickers = ["AAPL", "MSFT", "GOOG", "NVDA", "AMZN", "META", "TSLA", "JPM", "V", "XOM"]
    themes = [_theme(f"T{i}", [tickers[i]], score=(i + 1) / 10) for i in range(10)]
    brief = _brief(*themes)
    target = compute_target_allocation(brief, top_n=2)
    symbols = {r.symbol for r in target.rows}
    assert symbols == {"XOM", "V"}


def test_uses_brief_report_date() -> None:
    brief = _brief(_theme("X", ["AAPL"]))
    target = compute_target_allocation(brief)
    assert target.as_of == date(2026, 7, 1)
