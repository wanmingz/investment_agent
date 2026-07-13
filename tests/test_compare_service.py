"""Tests for Compare manual vs benchmark target."""

from __future__ import annotations

from datetime import date

from investment_agent.models import FinalTheme, InvestmentBrief, ThemeStage
from investment_agent.portfolio.compare.drift import compute_benchmark_drift_report
from investment_agent.portfolio.compare.service import evaluate_manual_vs_target
from investment_agent.portfolio.model.allocation import compute_model_target_allocation
from investment_agent.portfolio.models import PortfolioSnapshot, Position
from investment_agent.universe.constants import SECTOR_ETFS


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


def _snapshot(*positions: tuple[str, float]) -> PortfolioSnapshot:
    pos_models = [
        Position(
            symbol=sym,
            quantity=1.0,
            avg_cost=mv,
            cost_basis=mv,
            last_price=mv,
            market_value=mv,
        )
        for sym, mv in positions
    ]
    total = sum(mv for _, mv in positions)
    return PortfolioSnapshot(
        as_of=date(2026, 7, 1),
        positions=pos_models,
        total_cost_basis=total,
        total_market_value=total,
        total_nav=total,
        total_unrealized_pnl=0.0,
    )


def test_benchmark_drift_rolls_stock_into_sector_etf() -> None:
    brief = _brief(_theme("Tech growth", ["AAPL", "NVDA"], score=1.0))
    target = compute_model_target_allocation(brief)
    snap = _snapshot(("AAPL", 100.0))
    report, uncovered = compute_benchmark_drift_report(brief, snap, target)
    xlk = SECTOR_ETFS["Tech"]
    row = next(r for r in report.rows if r.symbol == xlk)
    assert row.actual_pct == 100.0
    assert row.target_pct == 100.0
    assert row.drift_pp == 0.0
    assert uncovered == 0.0


def test_benchmark_drift_tracks_uncovered_holdings() -> None:
    brief = _brief(_theme("Tech", ["AAPL"], score=1.0))
    target = compute_model_target_allocation(brief)
    snap = _snapshot(("XYZ", 100.0))
    report, uncovered = compute_benchmark_drift_report(brief, snap, target)
    xlk = next(r for r in report.rows if r.symbol == SECTOR_ETFS["Tech"])
    assert xlk.actual_pct == 0.0
    assert uncovered == 100.0


def test_evaluate_manual_vs_target_no_brief() -> None:
    outcome = evaluate_manual_vs_target(None)
    assert outcome.status == "no_brief"
