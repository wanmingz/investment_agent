"""Tests for manual vs model portfolio ledger isolation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from investment_agent.portfolio.db import db_path, resolve_db_path
from investment_agent.portfolio.ledger import add_trade, list_trades
from investment_agent.portfolio.models import TradeInput, TradeSide


def test_default_db_paths_differ() -> None:
    assert db_path("manual") != db_path("model")
    assert db_path("manual").name == "portfolio.db"
    assert db_path("model").name == "ai_portfolio.db"


def test_resolve_db_path_explicit_path_wins(tmp_path: Path) -> None:
    custom = tmp_path / "custom.db"
    assert resolve_db_path(custom, "model") == custom


def test_manual_and_model_trades_isolated(tmp_path: Path) -> None:
    manual_db = tmp_path / "manual.db"
    model_db = tmp_path / "model.db"
    d = date(2026, 3, 1)

    add_trade(
        TradeInput(symbol="AAPL", side=TradeSide.BUY, quantity=10, price=100, trade_date=d),
        path=manual_db,
    )
    add_trade(
        TradeInput(symbol="MSFT", side=TradeSide.BUY, quantity=5, price=200, trade_date=d),
        path=model_db,
    )

    manual_trades = list_trades(path=manual_db)
    model_trades = list_trades(path=model_db)

    assert len(manual_trades) == 1
    assert manual_trades[0].symbol == "AAPL"
    assert len(model_trades) == 1
    assert model_trades[0].symbol == "MSFT"


def test_ledger_kwarg_resolves_to_separate_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manual_db = tmp_path / "manual.db"
    model_db = tmp_path / "ai.db"
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(manual_db))
    monkeypatch.setenv("PORTFOLIO_AI_DB_PATH", str(model_db))
    d = date(2026, 3, 2)

    add_trade(
        TradeInput(symbol="SPY", side=TradeSide.BUY, quantity=1, price=400, trade_date=d),
        ledger="manual",
    )
    add_trade(
        TradeInput(symbol="QQQ", side=TradeSide.BUY, quantity=2, price=300, trade_date=d),
        ledger="model",
    )

    assert list_trades(ledger="manual")[0].symbol == "SPY"
    assert list_trades(ledger="model")[0].symbol == "QQQ"
    assert list_trades(path=manual_db)[0].symbol == "SPY"
