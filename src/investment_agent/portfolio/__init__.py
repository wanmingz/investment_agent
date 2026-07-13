"""Portfolio ledger — trade recording, positions, and performance."""

from investment_agent.portfolio.db import LedgerKind, db_path
from investment_agent.portfolio.ledger import (
    InsufficientSharesError,
    InvalidDeleteError,
    TradeNotFoundError,
    add_trade,
    compute_positions,
    delete_trade,
    get_open_positions,
    list_trades,
)
from investment_agent.portfolio.models import (
    PerformanceSummary,
    PortfolioSnapshot,
    Position,
    Trade,
    TradeInput,
    TradeSide,
    PerformanceComparePoint,
    model_name,
)
from investment_agent.portfolio.manual.theme_alignment import compute_theme_alignment
from investment_agent.portfolio.performance import (
    DEFAULT_COMPARE_START,
    compare_performance_series,
    get_marked_positions,
    mark_positions,
    summarize_performance,
)

__all__ = [
    "DEFAULT_COMPARE_START",
    "InsufficientSharesError",
    "InvalidDeleteError",
    "LedgerKind",
    "PerformanceComparePoint",
    "PerformanceSummary",
    "PortfolioSnapshot",
    "Position",
    "Trade",
    "TradeInput",
    "TradeSide",
    "TradeNotFoundError",
    "compare_performance_series",
    "compute_theme_alignment",
    "db_path",
    "model_name",
    "add_trade",
    "compute_positions",
    "delete_trade",
    "get_marked_positions",
    "get_open_positions",
    "list_trades",
    "mark_positions",
    "summarize_performance",
]
