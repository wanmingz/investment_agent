"""Pydantic models for the portfolio ledger."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from investment_agent.universe.symbols import is_likely_ticker


def model_name(obj: object) -> str:
    """Return ``name`` from Trade/Position; safe when field missing (e.g. Streamlit hot reload)."""
    val = getattr(obj, "name", "")
    return val if isinstance(val, str) else ""


def snapshot_cash_balance(snapshot: object) -> float:
    """Cash in portfolio account; safe when schema predates cash_balance field."""
    val = getattr(snapshot, "cash_balance", None)
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def snapshot_total_nav(snapshot: object) -> float:
    """Cash + holdings market value; safe when schema predates total_nav field."""
    val = getattr(snapshot, "total_nav", None)
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    mkt = getattr(snapshot, "total_market_value", None)
    market = float(mkt) if isinstance(mkt, (int, float)) else 0.0
    nav = market + snapshot_cash_balance(snapshot)
    return nav if nav > 0 else market


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeInput(BaseModel):
    symbol: str
    side: TradeSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    trade_date: date
    name: str = ""
    fees: float = Field(default=0.0, ge=0)
    notes: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        sym = v.strip().upper().lstrip("$")
        if not is_likely_ticker(sym):
            raise ValueError(f"Invalid ticker symbol: {v!r}")
        return sym


class Trade(TradeInput):
    id: int
    created_at: datetime


class Position(BaseModel):
    symbol: str
    name: str = ""
    quantity: float
    avg_cost: float
    cost_basis: float
    last_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None


class PortfolioSnapshot(BaseModel):
    as_of: date
    positions: list[Position]
    total_cost_basis: float
    total_market_value: float
    cash_balance: float = 0.0
    total_nav: float = 0.0
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float | None = None


class PerformanceSummary(BaseModel):
    as_of: date
    from_date: date | None = None
    to_date: date | None = None
    snapshot: PortfolioSnapshot
    realized_pnl: float
    total_pnl: float
    gross_invested: float
    total_return_pct: float | None = None
    spy_return_pct: float | None = None
    vs_spy_pct: float | None = None
    first_trade_date: date | None = None


class PerformanceComparePoint(BaseModel):
    date: date
    portfolio_index: float
    spy_index: float


class ThemeAlignmentRow(BaseModel):
    theme_name: str
    rank: int
    overlap_symbols: list[str] = Field(default_factory=list)
    overlap_pct: float = 0.0
    status: str  # high | partial | gap
    theme_tickers: list[str] = Field(default_factory=list)


class UncoveredPosition(BaseModel):
    symbol: str
    name: str = ""
    weight_pct: float = 0.0


class ThemeAlignmentReport(BaseModel):
    as_of: date
    rows: list[ThemeAlignmentRow] = Field(default_factory=list)
    uncovered_positions: list[UncoveredPosition] = Field(default_factory=list)
    gap_themes: list[str] = Field(default_factory=list)
    total_nav: float = 0.0
