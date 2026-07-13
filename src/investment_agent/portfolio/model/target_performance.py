"""Buy-and-hold index for score-weighted model target allocation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from investment_agent.dates import analysis_date
from investment_agent.portfolio.models import PerformanceComparePoint, TargetAllocation
from investment_agent.portfolio.performance import (
    DEFAULT_COMPARE_START,
    _fetch_close_series,
    _price_on_or_before,
    compare_performance_series,
)
from investment_agent.portfolio.db import LedgerKind
from investment_agent.universe.constants import BENCHMARK_SYMBOL


def target_allocation_performance_series(
    target: TargetAllocation,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[PerformanceComparePoint]:
    """
    Chain-linked index for a static target-weight portfolio vs SPY.

    Assumes full investment at the first day on or after ``target.as_of`` when
    all target symbols have prices. Weights follow ``target_pct`` (normalized).
    """
    from_date = from_date or DEFAULT_COMPARE_START
    to_date = to_date or analysis_date()
    range_start = max(from_date, target.as_of)
    if to_date < range_start:
        return []

    weights = {r.symbol.upper(): r.target_pct for r in target.rows if r.target_pct > 0}
    if not weights:
        return []

    symbols = sorted(weights)
    weight_total = sum(weights.values())
    if weight_total <= 0:
        return []

    spy_series = _fetch_close_series(BENCHMARK_SYMBOL, range_start, to_date)
    if not spy_series:
        return []

    price_maps: dict[str, dict[date, float]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        futures = {
            pool.submit(_fetch_close_series, sym, range_start, to_date): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            price_maps[sym] = fut.result()

    trading_days = sorted(spy_series)
    start_idx: int | None = None
    base_prices: dict[str, float] = {}
    for i, d in enumerate(trading_days):
        day_prices = {
            sym: _price_on_or_before(price_maps.get(sym, {}), d) for sym in symbols
        }
        if all(px is not None and px > 0 for px in day_prices.values()):
            start_idx = i
            base_prices = {sym: float(day_prices[sym]) for sym in symbols}  # type: ignore[arg-type]
            break

    if start_idx is None:
        return []

    start_day = trading_days[start_idx]
    spy_base = spy_series[start_day]

    points: list[PerformanceComparePoint] = []
    for i, d in enumerate(trading_days):
        if i < start_idx:
            port_index = 100.0
        else:
            port_index = (
                100.0
                * sum(
                    weights[sym]
                    * float(_price_on_or_before(price_maps.get(sym, {}), d) or base_prices[sym])
                    / base_prices[sym]
                    for sym in symbols
                )
                / weight_total
            )
        spy_index = 100.0 * spy_series[d] / spy_base if spy_base else 100.0
        points.append(
            PerformanceComparePoint(
                date=d,
                portfolio_index=port_index,
                spy_index=spy_index,
            )
        )
    return points


def model_performance_series(
    target: TargetAllocation,
    *,
    ledger: LedgerKind = "model",
    from_date: date | None = None,
    to_date: date | None = None,
) -> tuple[list[PerformanceComparePoint], list[PerformanceComparePoint] | None]:
    """Target-weight index and optional paper-ledger index (same SPY rebasing window)."""
    target_points = target_allocation_performance_series(
        target, from_date=from_date, to_date=to_date
    )
    if not target_points:
        return [], None

    ledger_points = compare_performance_series(
        from_date=from_date, to_date=to_date, ledger=ledger
    )
    if not ledger_points:
        return target_points, None

    ledger_by_date = {p.date: p.portfolio_index for p in ledger_points}
    first_ledger_idx = next(
        (i for i, p in enumerate(target_points) if p.date in ledger_by_date),
        None,
    )
    if first_ledger_idx is None:
        return target_points, None

    base_day = target_points[first_ledger_idx].date
    base_ledger = ledger_by_date[base_day]
    if base_ledger <= 0:
        return target_points, None

    aligned: list[PerformanceComparePoint] = []
    for pt in target_points:
        if pt.date not in ledger_by_date:
            continue
        scaled = 100.0 * ledger_by_date[pt.date] / base_ledger
        aligned.append(
            PerformanceComparePoint(
                date=pt.date,
                portfolio_index=scaled,
                spy_index=pt.spy_index,
            )
        )
    return target_points, aligned if aligned else None
