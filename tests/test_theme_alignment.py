"""Tests for theme–portfolio alignment."""

from __future__ import annotations

from datetime import date

import pytest

from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.portfolio.models import PortfolioSnapshot, Position
from investment_agent.portfolio.manual.theme_alignment import compute_theme_alignment


def _theme(name: str, tickers: list[str], score: float = 1.5) -> FinalTheme:
    inv = score / 2
    return FinalTheme(
        name=name,
        thesis="t",
        stage=ThemeStage.MID,
        consensus_score=inv,
        investability_score=inv,
        synthesis="s",
        key_drivers=[],
        risks=[],
        tickers_or_sectors=tickers,
    )


def _brief(*themes: FinalTheme) -> InvestmentBrief:
    return InvestmentBrief(
        report_date="2026-07-08",
        as_of_context="As of 2026-07-08",
        executive_summary="x",
        regime_view="r",
        themes=list(themes),
    )


def _snapshot(*positions: Position) -> PortfolioSnapshot:
    total_mkt = sum(p.market_value or p.cost_basis for p in positions)
    return PortfolioSnapshot(
        as_of=date(2026, 7, 8),
        positions=list(positions),
        total_cost_basis=total_mkt,
        total_market_value=total_mkt,
        total_nav=total_mkt,
        total_unrealized_pnl=0.0,
    )


def test_ticker_overlap_aapl() -> None:
    brief = _brief(_theme("AI Leaders", ["AAPL", "NVDA"]))
    snap = _snapshot(
        Position(
            symbol="AAPL",
            quantity=10,
            avg_cost=100,
            cost_basis=1000,
            market_value=1100,
        )
    )
    report = compute_theme_alignment(brief, snap)
    assert len(report.rows) == 1
    assert report.rows[0].overlap_symbols == ["AAPL"]
    assert report.rows[0].status in ("partial", "high")
    assert report.rows[0].overlap_pct == pytest.approx(100.0)
    assert report.uncovered_positions == []
    assert report.gap_themes == []


def test_sector_overlap_via_etf() -> None:
    brief = _brief(_theme("Tech rally", ["XLK", "Tech"]))
    snap = _snapshot(
        Position(
            symbol="XLK",
            quantity=20,
            avg_cost=50,
            cost_basis=1000,
            market_value=1000,
        )
    )
    report = compute_theme_alignment(brief, snap)
    assert report.rows[0].overlap_symbols == ["XLK"]
    assert report.rows[0].overlap_pct == pytest.approx(100.0)


def test_gap_theme_and_uncovered_holding() -> None:
    brief = _brief(
        _theme("Energy", ["XLE"], score=1.6),
        _theme("Unrelated", ["GLD"], score=0.8),
    )
    snap = _snapshot(
        Position(
            symbol="AAPL",
            quantity=5,
            avg_cost=100,
            cost_basis=500,
            market_value=500,
        )
    )
    report = compute_theme_alignment(brief, snap, top_n=2)
    assert report.gap_themes == ["Energy", "Unrelated"]
    assert len(report.uncovered_positions) == 1
    assert report.uncovered_positions[0].symbol == "AAPL"


def test_high_overlap_threshold() -> None:
    brief = _brief(_theme("Mixed", ["AAPL", "MSFT"]))
    snap = _snapshot(
        Position(symbol="AAPL", quantity=1, avg_cost=100, cost_basis=100, market_value=300),
        Position(symbol="MSFT", quantity=1, avg_cost=100, cost_basis=100, market_value=700),
    )
    report = compute_theme_alignment(brief, snap)
    assert report.rows[0].overlap_pct == pytest.approx(100.0)
    assert report.rows[0].status == "high"
