"""Tests for portfolio drift vs target."""

from __future__ import annotations

from datetime import date

from investment_agent.portfolio.compare.drift import compute_drift_report
from investment_agent.portfolio.models import (
    PortfolioSnapshot,
    Position,
    TargetAllocation,
    TargetWeightRow,
)


def _snapshot(
    positions: list[tuple[str, float, float]],
    *,
    cash: float = 0.0,
) -> PortfolioSnapshot:
    pos_models = [
        Position(
            symbol=sym,
            quantity=1.0,
            avg_cost=mv,
            cost_basis=mv,
            last_price=mv,
            market_value=mv,
        )
        for sym, mv, _ in positions
    ]
    market = sum(mv for _, mv, _ in positions)
    nav = market + cash
    return PortfolioSnapshot(
        as_of=date(2026, 7, 1),
        positions=pos_models,
        total_cost_basis=market,
        total_market_value=market,
        cash_balance=cash,
        total_nav=nav,
        total_unrealized_pnl=0.0,
    )


def _target(rows: list[tuple[str, float]]) -> TargetAllocation:
    return TargetAllocation(
        as_of=date(2026, 7, 1),
        top_n=8,
        rows=[TargetWeightRow(symbol=s, target_pct=p) for s, p in rows],
        total_target_pct=sum(p for _, p in rows),
    )


def test_drift_on_target_symbols() -> None:
    snap = _snapshot([("AAPL", 60.0, 0.0), ("MSFT", 40.0, 0.0)])
    target = _target([("AAPL", 50.0), ("MSFT", 50.0)])
    report = compute_drift_report(snap, target, band_pp=5.0)
    by_sym = {r.symbol: r for r in report.rows}
    assert by_sym["AAPL"].actual_pct == 60.0
    assert by_sym["AAPL"].drift_pp == 10.0
    assert by_sym["AAPL"].severity == "alert"
    assert by_sym["MSFT"].drift_pp == -10.0


def test_drift_ok_within_band() -> None:
    snap = _snapshot([("AAPL", 52.0, 0.0), ("MSFT", 48.0, 0.0)])
    target = _target([("AAPL", 50.0), ("MSFT", 50.0)])
    report = compute_drift_report(snap, target, band_pp=5.0)
    assert all(r.severity == "ok" for r in report.rows)


def test_drift_includes_untargeted_holdings() -> None:
    snap = _snapshot([("AAPL", 50.0, 0.0), ("XYZ", 50.0, 0.0)])
    target = _target([("AAPL", 100.0)])
    report = compute_drift_report(snap, target)
    by_sym = {r.symbol: r for r in report.rows}
    assert by_sym["XYZ"].target_pct == 0.0
    assert by_sym["XYZ"].actual_pct == 50.0
    assert by_sym["XYZ"].drift_pp == 50.0
