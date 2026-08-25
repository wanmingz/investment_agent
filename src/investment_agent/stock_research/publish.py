"""Publish a stock memo for Streamlit Cloud (tracked under brief/)."""

from __future__ import annotations

from pathlib import Path

from investment_agent.stock_research.models import InvestmentMemo
from investment_agent.stock_research.storage import (
    latest_path,
    load_memo,
    published_path,
    save_memo,
)

DEFAULT_EXAMPLE_TICKER = "AAPL"


def publish_memo(
    ticker: str = DEFAULT_EXAMPLE_TICKER,
    *,
    memo: InvestmentMemo | None = None,
    path: Path | None = None,
) -> Path:
    """Copy a local memo into brief/stock_{TICKER}_latest.json for Cloud friends."""
    sym = ticker.strip().upper()
    payload = memo or load_memo(path=latest_path(sym))
    if payload is None:
        raise ValueError(f"No saved memo for {sym}. Run: invest-stock {sym}")
    if payload.ticker.strip().upper() != sym:
        raise ValueError(f"Memo ticker {payload.ticker!r} does not match publish ticker {sym!r}.")
    target = path or published_path(sym)
    return save_memo(payload, target)


def load_published(
    ticker: str = DEFAULT_EXAMPLE_TICKER,
    *,
    path: Path | None = None,
) -> InvestmentMemo | None:
    return load_memo(path=path or published_path(ticker))
