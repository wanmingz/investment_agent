"""Model portfolio target allocation (sector ETFs / SPY only)."""

from __future__ import annotations

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.compare.allocation import compute_target_allocation
from investment_agent.portfolio.models import TargetAllocation


def compute_model_target_allocation(
    brief: InvestmentBrief,
    *,
    top_n: int = 8,
    investable_pct: float = 100.0,
) -> TargetAllocation:
    """Score-weighted targets using sector ETFs and SPY — no single-stock names."""
    return compute_target_allocation(
        brief,
        top_n=top_n,
        investable_pct=investable_pct,
        instrument_mode="benchmark",
    )
