"""Unit tests for portfolio ledger and performance."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from investment_agent.agents.markets.price import PriceMetrics
from investment_agent.portfolio.quotes import fetch_close_on_date
from investment_agent.portfolio import db
from investment_agent.portfolio.ledger import (
    InsufficientSharesError,
    InvalidDeleteError,
    TradeNotFoundError,
    add_trade,
    compute_positions,
    delete_trade,
    get_open_positions,
)
from investment_agent.portfolio.models import Trade, TradeInput, TradeSide
from investment_agent.portfolio.performance import mark_positions, summarize_performance


def _trade(
    trade_id: int,
    symbol: str,
    side: TradeSide,
    qty: float,
    price: float,
    trade_date: date,
    fees: float = 0.0,
) -> Trade:
    from datetime import datetime

    return Trade(
        id=trade_id,
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        fees=fees,
        trade_date=trade_date,
        notes="",
        name="",
        created_at=datetime(2026, 1, 1),
    )


@pytest.fixture
def portfolio_db(tmp_path: Path) -> Path:
    path = tmp_path / "portfolio.db"
    db.init_db(path)
    return path


def test_weighted_average_cost(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=120, trade_date=d),
        path=portfolio_db,
    )
    positions = get_open_positions(path=portfolio_db)
    assert len(positions) == 1
    assert positions[0].quantity == 20
    assert positions[0].avg_cost == pytest.approx(110.0)
    assert positions[0].cost_basis == pytest.approx(2200.0)


def test_partial_sell_realized_pnl(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=120, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.SELL, quantity=5, price=130, trade_date=d),
        path=portfolio_db,
    )
    positions = get_open_positions(path=portfolio_db)
    assert len(positions) == 1
    assert positions[0].quantity == 15
    assert positions[0].avg_cost == pytest.approx(110.0)

    trades = db.fetch_trades(path=portfolio_db)
    _, realized = compute_positions(trades)
    assert realized == pytest.approx(5 * (130 - 110))


def test_full_close_empty_positions(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    add_trade(
        TradeInput(symbol="MSFT", side=TradeSide.BUY, quantity=10, price=50, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="MSFT", side=TradeSide.SELL, quantity=10, price=60, trade_date=d),
        path=portfolio_db,
    )
    assert get_open_positions(path=portfolio_db) == []


def test_sell_exceeding_holdings_raises(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=5, price=100, trade_date=d),
        path=portfolio_db,
    )
    with pytest.raises(InsufficientSharesError):
        add_trade(
            TradeInput(symbol="AAPL", side=TradeSide.SELL, quantity=10, price=110, trade_date=d),
            path=portfolio_db,
        )


def test_db_init_idempotent(portfolio_db: Path) -> None:
    db.init_db(portfolio_db)
    db.init_db(portfolio_db)
    add_trade(
        TradeInput(symbol="SPY", side=TradeSide.BUY, quantity=1, price=400, trade_date=date.today()),
        path=portfolio_db,
    )
    assert len(db.fetch_trades(path=portfolio_db)) == 1


def test_mark_positions_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from investment_agent.portfolio.models import Position

    positions = [
        Position(symbol="AAPL", name="Apple Inc.", quantity=10, avg_cost=100.0, cost_basis=1000.0),
    ]

    def fake_fetch(symbol: str, *, spy_return_20d=None, label: str = "") -> PriceMetrics:
        return PriceMetrics(symbol=symbol, label=symbol, last_close=110.0)

    monkeypatch.setattr(
        "investment_agent.portfolio.performance.fetch_price_metrics",
        fake_fetch,
    )
    snap = mark_positions(positions, as_of=date(2026, 3, 1))
    assert snap.positions[0].market_value == pytest.approx(1100.0)
    assert snap.positions[0].unrealized_pnl == pytest.approx(100.0)
    assert snap.positions[0].unrealized_pnl_pct == pytest.approx(10.0)


def test_summarize_performance_mocked(portfolio_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = date(2026, 1, 10)
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=portfolio_db,
    )

    def fake_fetch(symbol: str, *, spy_return_20d=None, label: str = "") -> PriceMetrics:
        return PriceMetrics(symbol=symbol, label=symbol, last_close=110.0)

    monkeypatch.setattr(
        "investment_agent.portfolio.performance.fetch_price_metrics",
        fake_fetch,
    )
    monkeypatch.setattr(
        "investment_agent.portfolio.performance._spy_return_since",
        lambda start, end: 5.0,
    )

    summary = summarize_performance(path=portfolio_db)
    assert summary.gross_invested == pytest.approx(1000.0)
    assert summary.snapshot.total_unrealized_pnl == pytest.approx(100.0)
    assert summary.total_pnl == pytest.approx(100.0)
    assert summary.spy_return_pct == pytest.approx(5.0)
    assert summary.vs_spy_pct == pytest.approx(5.0)


def test_delete_trade(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    t1 = add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=5, price=110, trade_date=d),
        path=portfolio_db,
    )
    removed = delete_trade(t1.id, path=portfolio_db)
    assert removed.id == t1.id
    positions = get_open_positions(path=portfolio_db)
    assert len(positions) == 1
    assert positions[0].quantity == 5
    assert positions[0].avg_cost == pytest.approx(110.0)
    assert len(db.fetch_trades(path=portfolio_db)) == 1


def test_delete_trade_not_found(portfolio_db: Path) -> None:
    with pytest.raises(TradeNotFoundError):
        delete_trade(999, path=portfolio_db)


def test_delete_trade_orphans_sell(portfolio_db: Path) -> None:
    d = date(2026, 1, 10)
    buy = add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=portfolio_db,
    )
    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.SELL, quantity=5, price=120, trade_date=d),
        path=portfolio_db,
    )
    with pytest.raises(InvalidDeleteError):
        delete_trade(buy.id, path=portfolio_db)


def test_fetch_close_on_date_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    idx = pd.to_datetime(["2026-01-08", "2026-01-09"])
    fake_hist = pd.DataFrame({"Close": [150.0, 155.25]}, index=idx)

    class FakeTicker:
        def history(self, **kwargs):
            return fake_hist

    monkeypatch.setattr("yfinance.Ticker", lambda sym: FakeTicker())
    assert fetch_close_on_date("AAPL", date(2026, 1, 9)) == pytest.approx(155.25)
    assert fetch_close_on_date("AAPL", date(2026, 1, 10)) == pytest.approx(155.25)
    assert fetch_close_on_date("", date(2026, 1, 9)) is None


def test_add_trade_auto_fetches_name(
    portfolio_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "investment_agent.portfolio.ledger.fetch_symbol_name",
        lambda sym: "Apple Inc." if sym == "AAPL" else "",
    )
    stored = add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=1, price=100, trade_date=date(2026, 1, 10)),
        path=portfolio_db,
    )
    assert stored.name == "Apple Inc."
    positions = get_open_positions(path=portfolio_db)
    assert positions[0].name == "Apple Inc."


def test_db_migration_adds_name_column(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.db"
    import sqlite3

    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (1);
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            fees REAL NOT NULL DEFAULT 0,
            trade_date TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    conn.close()

    db.init_db(legacy)
    with sqlite3.connect(legacy) as conn:
        assert "name" in db._table_columns(conn, "trades")  # noqa: SLF001
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 2


def test_compare_performance_series_mocked(
    portfolio_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pandas as pd

    from investment_agent.portfolio.performance import (
        DEFAULT_COMPARE_START,
        compare_performance_series,
    )

    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=date(2026, 7, 2)),
        path=portfolio_db,
    )

    idx = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03"])
    spy_hist = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)
    aapl_hist = pd.DataFrame({"Close": [50.0, 100.0, 110.0]}, index=idx)

    def fake_series(symbol: str, start: date, end: date) -> dict[date, float]:
        if symbol == "SPY":
            return {ts.date(): float(spy_hist.loc[ts, "Close"]) for ts in spy_hist.index}
        if symbol == "AAPL":
            return {ts.date(): float(aapl_hist.loc[ts, "Close"]) for ts in aapl_hist.index}
        return {}

    monkeypatch.setattr(
        "investment_agent.portfolio.performance._fetch_close_series",
        fake_series,
    )
    monkeypatch.setattr(
        "investment_agent.portfolio.performance.analysis_date",
        lambda: date(2026, 7, 3),
    )

    points = compare_performance_series(from_date=DEFAULT_COMPARE_START, path=portfolio_db)
    assert len(points) == 3
    assert points[0].spy_index == pytest.approx(100.0)
    assert points[0].portfolio_index == pytest.approx(100.0)
    assert points[1].portfolio_index == pytest.approx(100.0)
    assert points[2].portfolio_index == pytest.approx(110.0)
    assert points[2].spy_index == pytest.approx(102.0)
