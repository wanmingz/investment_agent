"""Compare manual holdings vs brief target weights."""

from investment_agent.portfolio.compare.allocation import compute_target_allocation
from investment_agent.portfolio.compare.drift import (
    compute_benchmark_drift_report,
    compute_drift_report,
)
from investment_agent.portfolio.compare.service import CompareOutcome, evaluate_manual_vs_target

VIEW_LABEL = "Compare"

__all__ = [
    "VIEW_LABEL",
    "CompareOutcome",
    "compute_target_allocation",
    "compute_benchmark_drift_report",
    "compute_drift_report",
    "evaluate_manual_vs_target",
]
