"""Tests for published portfolio snapshot."""

from datetime import date, datetime
from pathlib import Path

import pytest

from investment_agent.portfolio.ledger import add_trade
from investment_agent.portfolio.models import TradeInput, TradeSide
from investment_agent.portfolio.publish import (
    load_published,
    publish_manual_portfolio,
    should_use_published,
)


def test_publish_and_load_roundtrip(tmp_path, monkeypatch) -> None:
    db = tmp_path / "portfolio.db"
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(db))
    published = tmp_path / "portfolio_latest.json"
    monkeypatch.setattr(
        "investment_agent.portfolio.publish.PUBLISHED_PATH",
        published,
    )

    add_trade(
        TradeInput(
            symbol="AAPL",
            side=TradeSide.BUY,
            quantity=10,
            price=100.0,
            trade_date=date(2026, 1, 15),
            name="Apple",
        ),
        ledger="manual",
    )

    from investment_agent.portfolio.models import (
        PerformanceSummary,
        PortfolioSnapshot,
        Position,
    )

    snap = PortfolioSnapshot(
        as_of=date(2026, 8, 4),
        positions=[
            Position(
                symbol="AAPL",
                name="Apple",
                quantity=10,
                avg_cost=100.0,
                cost_basis=1000.0,
                last_price=110.0,
                market_value=1100.0,
                unrealized_pnl=100.0,
                unrealized_pnl_pct=10.0,
            )
        ],
        total_cost_basis=1000.0,
        total_market_value=1100.0,
        cash_balance=0.0,
        total_nav=1100.0,
        total_unrealized_pnl=100.0,
        total_unrealized_pnl_pct=10.0,
    )
    summary = PerformanceSummary(
        as_of=date(2026, 8, 4),
        snapshot=snap,
        realized_pnl=0.0,
        total_pnl=100.0,
        gross_invested=1000.0,
        total_return_pct=10.0,
        first_trade_date=date(2026, 1, 15),
    )
    monkeypatch.setattr(
        "investment_agent.portfolio.publish.summarize_performance",
        lambda **kwargs: summary,
    )

    out = publish_manual_portfolio(
        path=published,
        now=datetime(2026, 8, 4, 12, 0, 0),
    )
    assert out == published
    loaded = load_published(published)
    assert loaded is not None
    assert loaded.published_at.startswith("2026-08-04")
    assert len(loaded.trades) == 1
    assert loaded.trades[0].symbol == "AAPL"
    assert loaded.summary is not None
    assert loaded.summary.total_pnl == 100.0
    assert should_use_published(ledger="manual") is False

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "empty.db"))
    assert should_use_published(ledger="manual") is True

    from investment_agent.portfolio.publish import (
        live_summary_from_published,
        materialize_published_db,
    )

    mat = tmp_path / "mat.db"
    materialize_published_db(loaded, path=mat)
    assert mat.is_file()
    monkeypatch.setattr(
        "investment_agent.portfolio.publish.summarize_performance",
        lambda **kwargs: summary,
    )
    live, path = live_summary_from_published(loaded, db_path=mat)
    assert live.total_pnl == 100.0
    assert path == mat


def test_publish_requires_trades(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "empty.db"))
    monkeypatch.setattr(
        "investment_agent.portfolio.publish.PUBLISHED_PATH",
        tmp_path / "out.json",
    )
    with pytest.raises(ValueError, match="No manual trades"):
        publish_manual_portfolio()
