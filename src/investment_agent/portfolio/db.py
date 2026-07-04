"""SQLite persistence for portfolio trades."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from investment_agent.portfolio.models import Trade, TradeInput, TradeSide

SCHEMA_VERSION = 2

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "reports" / "portfolio.db"


def db_path() -> Path:
    override = os.environ.get("PORTFOLIO_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_DB


@contextmanager
def connect(path: Path | None = None):
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _apply_migrations(conn: sqlite3.Connection, current: int) -> None:
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Portfolio DB schema version {current} is newer than supported {SCHEMA_VERSION}. "
            "Upgrade the application."
        )
    if current < 2:
        cols = _table_columns(conn, "trades")
        if "name" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE schema_version SET version = 2")
        current = 2
    if current != SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported portfolio DB schema version {current} "
            f"(expected {SCHEMA_VERSION}). Back up and migrate manually."
        )


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                quantity REAL NOT NULL CHECK (quantity > 0),
                price REAL NOT NULL CHECK (price > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK (fees >= 0),
                trade_date TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
            """
        )
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            cols = _table_columns(conn, "trades")
            if "name" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        else:
            _apply_migrations(conn, row["version"])


def _row_to_trade(row: sqlite3.Row) -> Trade:
    keys = row.keys()
    return Trade(
        id=row["id"],
        symbol=row["symbol"],
        side=TradeSide(row["side"]),
        quantity=row["quantity"],
        price=row["price"],
        fees=row["fees"],
        trade_date=date.fromisoformat(row["trade_date"]),
        name=(row["name"] or "") if "name" in keys else "",
        notes=row["notes"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def insert_trade(trade: TradeInput, *, path: Path | None = None) -> Trade:
    init_db(path)
    now = datetime.now().replace(microsecond=0).isoformat()
    with connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO trades (symbol, side, quantity, price, fees, trade_date, name, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.symbol,
                trade.side.value,
                trade.quantity,
                trade.price,
                trade.fees,
                trade.trade_date.isoformat(),
                trade.name,
                trade.notes,
                now,
            ),
        )
        trade_id = cur.lastrowid
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    assert row is not None
    return _row_to_trade(row)


def fetch_trades(
    *,
    symbol: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    path: Path | None = None,
) -> list[Trade]:
    init_db(path)
    clauses: list[str] = []
    params: list[object] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.strip().upper())
    if from_date:
        clauses.append("trade_date >= ?")
        params.append(from_date.isoformat())
    if to_date:
        clauses.append("trade_date <= ?")
        params.append(to_date.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(path) as conn:
        rows = conn.execute(
            f"SELECT * FROM trades {where} ORDER BY trade_date, id",
            params,
        ).fetchall()
    return [_row_to_trade(r) for r in rows]


def fetch_trade_by_id(trade_id: int, *, path: Path | None = None) -> Trade | None:
    init_db(path)
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    return _row_to_trade(row) if row else None


def delete_trade_by_id(trade_id: int, *, path: Path | None = None) -> bool:
    init_db(path)
    with connect(path) as conn:
        cur = conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        return cur.rowcount > 0
