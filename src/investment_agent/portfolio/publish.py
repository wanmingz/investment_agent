"""Publish manual portfolio snapshot for Streamlit Cloud (read-only)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from investment_agent.portfolio.db import LedgerKind
from investment_agent.portfolio.ledger import list_trades
from investment_agent.portfolio.models import PerformanceSummary, Trade
from investment_agent.portfolio.performance import summarize_performance

# Tracked next to theme brief — gitignored reports/ is unavailable on Cloud.
PUBLISHED_PATH = Path(__file__).resolve().parents[3] / "brief" / "portfolio_latest.json"


class PublishedPortfolio(BaseModel):
    """Frozen manual-ledger snapshot for public / Cloud read-only view."""

    schema_version: int = 1
    ledger: LedgerKind = "manual"
    published_at: str = ""
    note: str = (
        "Read-only snapshot for Streamlit Cloud. "
        "Refresh with: invest-portfolio publish"
    )
    trades: list[Trade] = Field(default_factory=list)
    summary: PerformanceSummary


def publish_manual_portfolio(
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Write brief/portfolio_latest.json from the local manual ledger."""
    trades = list_trades(ledger="manual")
    if not trades:
        raise ValueError("No manual trades to publish. Record trades first.")
    summary = summarize_performance(ledger="manual")
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
    """Show published snapshot when the local manual ledger has no trades."""
    if ledger != "manual":
        return False
    if list_trades(ledger="manual"):
        return False
    return load_published() is not None
