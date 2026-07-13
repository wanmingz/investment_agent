"""Tests for model target-weight performance index."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from investment_agent.portfolio.model.target_performance import (
    target_allocation_performance_series,
)
from investment_agent.portfolio.models import TargetAllocation, TargetWeightRow


def _target(rows: list[tuple[str, float]], as_of: date = date(2026, 7, 1)) -> TargetAllocation:
    weight_rows = [TargetWeightRow(symbol=s, target_pct=p) for s, p in rows]
    total = sum(p for _, p in rows)
    return TargetAllocation(as_of=as_of, top_n=8, rows=weight_rows, total_target_pct=total)


def test_target_performance_equal_weight_two_names(monkeypatch: pytest.MonkeyPatch) -> None:
    target = _target([("AAPL", 50.0), ("MSFT", 50.0)])

    idx = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03"])
    spy_hist = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)
    aapl_hist = pd.DataFrame({"Close": [100.0, 110.0, 120.0]}, index=idx)
    msft_hist = pd.DataFrame({"Close": [100.0, 90.0, 100.0]}, index=idx)

    def fake_series(symbol: str, start: date, end: date) -> dict[date, float]:
        if symbol == "SPY":
            return {ts.date(): float(spy_hist.loc[ts, "Close"]) for ts in spy_hist.index}
        if symbol == "AAPL":
            return {ts.date(): float(aapl_hist.loc[ts, "Close"]) for ts in aapl_hist.index}
        if symbol == "MSFT":
            return {ts.date(): float(msft_hist.loc[ts, "Close"]) for ts in msft_hist.index}
        return {}

    monkeypatch.setattr(
        "investment_agent.portfolio.model.target_performance._fetch_close_series",
        fake_series,
    )
    monkeypatch.setattr(
        "investment_agent.portfolio.model.target_performance.analysis_date",
        lambda: date(2026, 7, 3),
    )

    points = target_allocation_performance_series(target)
    assert len(points) == 3
    assert points[0].portfolio_index == pytest.approx(100.0)
    # Day 2: 50% * 1.10 + 50% * 0.90 = 1.00 -> still 100
    assert points[1].portfolio_index == pytest.approx(100.0)
    # Day 3: 50% * 1.20 + 50% * 1.00 = 1.10 -> 110
    assert points[2].portfolio_index == pytest.approx(110.0)


def test_target_performance_empty_when_no_symbols() -> None:
    target = TargetAllocation(as_of=date(2026, 7, 1), top_n=8, rows=[], total_target_pct=0.0)
    assert target_allocation_performance_series(target) == []
