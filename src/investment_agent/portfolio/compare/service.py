"""Manual portfolio vs brief target — programmatic compare (no Streamlit)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from investment_agent.models import InvestmentBrief
from investment_agent.portfolio.compare.allocation import compute_target_allocation
from investment_agent.portfolio.compare.drift import compute_benchmark_drift_report
from investment_agent.portfolio.manual import LEDGER as MANUAL_LEDGER
from investment_agent.portfolio.performance import summarize_performance

CompareStatus = Literal["no_brief", "no_trades", "ok", "empty"]


@dataclass(frozen=True)
class CompareOutcome:
    status: CompareStatus
    message: str | None = None
    table_rows: list[dict[str, str]] | None = None
    uncovered_pct: float | None = None


def evaluate_manual_vs_target(brief: InvestmentBrief | None) -> CompareOutcome:
    """Build drift table: manual holdings (rolled up) vs benchmark targets from brief."""
    if brief is None:
        return CompareOutcome(
            status="no_brief",
            message=(
                "Load a theme brief (Themes → Load last result or run analysis) "
                "to compare holdings against research targets."
            ),
        )

    try:
        summary = summarize_performance(ledger=MANUAL_LEDGER)
    except RuntimeError as e:
        return CompareOutcome(status="empty", message=f"Database error: {e}")

    if summary.first_trade_date is None:
        return CompareOutcome(
            status="no_trades",
            message="No manual trades yet. Record trades under My portfolio first.",
        )

    target = compute_target_allocation(brief, instrument_mode="benchmark")
    if not target.rows:
        return CompareOutcome(
            status="empty",
            message="No sector benchmarks mapped from top brief themes.",
        )

    report, uncovered_pct = compute_benchmark_drift_report(
        brief, summary.snapshot, target
    )
    if not report.rows:
        return CompareOutcome(status="empty", message="No drift rows.")

    table_rows = [
        {
            "ETF": row.symbol,
            "Target %": f"{row.target_pct:.1f}",
            "Actual %": f"{row.actual_pct:.1f}",
            "Drift (pp)": f"{row.drift_pp:+.1f}",
            "Severity": row.severity,
        }
        for row in report.rows
    ]
    return CompareOutcome(
        status="ok",
        table_rows=table_rows,
        uncovered_pct=uncovered_pct if uncovered_pct > 0.01 else None,
    )
