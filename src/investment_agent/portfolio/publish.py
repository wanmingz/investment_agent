"""Publish manual portfolio trades for Streamlit Cloud (live mark-to-market)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from investment_agent.portfolio import db as portfolio_db
from investment_agent.portfolio.db import LedgerKind
from investment_agent.portfolio.ledger import list_trades
from investment_agent.portfolio.models import PerformanceSummary, Trade, TradeInput
from investment_agent.portfolio.performance import summarize_performance

# Tracked next to theme brief — gitignored reports/ is unavailable on Cloud.
PUBLISHED_PATH = Path(__file__).resolve().parents[3] / "brief" / "portfolio_latest.json"
# Ephemeral DB rebuilt from published trades for live MTM on Cloud.
_MATERIALIZED_DB = (
    Path(__file__).resolve().parents[3] / "reports" / "cache" / "published_manual.db"
)


class PublishedPortfolio(BaseModel):
    """Published trade list for Cloud; UI re-marks prices live via yfinance."""

    schema_version: int = 1
    ledger: LedgerKind = "manual"
    published_at: str = ""
    note: str = (
        "Trade list for Streamlit Cloud. Dashboard mark-to-markets live with yfinance. "
        "Refresh trades with: invest-portfolio publish"
    )
    trades: list[Trade] = Field(default_factory=list)
    # Optional frozen summary (fallback if live MTM fails); not shown when live works.
    summary: PerformanceSummary | None = None


def publish_manual_portfolio(
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Write brief/portfolio_latest.json from the local manual ledger."""
    trades = list_trades(ledger="manual")
    if not trades:
        raise ValueError("No manual trades to publish. Record trades first.")
    # Keep a frozen summary as offline fallback; Cloud prefers live MTM from trades.
    try:
        summary = summarize_performance(ledger="manual")
    except Exception:  # noqa: BLE001
        summary = None
    stamp = (now or datetime.now().astimezone()).replace(microsecond=0).isoformat()
    payload = PublishedPortfolio(
        published_at=stamp,
        trades=trades,
        summary=summary,
    )
    target = path or PUBLISHED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        payload.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def load_published(path: Path | None = None) -> PublishedPortfolio | None:
    target = path or PUBLISHED_PATH
    if not target.is_file():
        return None
    try:
        return PublishedPortfolio.model_validate_json(
            target.read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001
        return None


def should_use_published(*, ledger: LedgerKind = "manual") -> bool:
    """Show published portfolio when the local manual ledger has no trades."""
    if ledger != "manual":
        return False
    if list_trades(ledger="manual"):
        return False
    return load_published() is not None


def materialize_published_db(
    published: PublishedPortfolio,
    *,
    path: Path | None = None,
) -> Path:
    """Rebuild a SQLite ledger from published trades (for live summarize_performance)."""
    target = path or _MATERIALIZED_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        target.unlink()
    portfolio_db.init_db(target)
    for t in published.trades:
        portfolio_db.insert_trade(
            TradeInput(
                symbol=t.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                trade_date=t.trade_date,
                name=t.name,
                fees=t.fees,
                notes=t.notes,
            ),
            path=target,
        )
    return target


def live_summary_from_published(
    published: PublishedPortfolio,
    *,
    db_path: Path | None = None,
) -> tuple[PerformanceSummary, Path]:
    """Mark-to-market published trades with current prices."""
    target = materialize_published_db(published, path=db_path)
    return summarize_performance(path=target), target
