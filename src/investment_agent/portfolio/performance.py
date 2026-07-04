"""Mark-to-market and performance summary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

from investment_agent.agents.markets.price import PriceMetrics, fetch_price_metrics
from investment_agent.portfolio.quotes import fetch_symbol_name
from investment_agent.dates import analysis_date
from investment_agent.portfolio import db
from investment_agent.portfolio.ledger import (
    compute_positions,
    compute_realized_pnl_in_range,
    get_open_positions,
    gross_invested,
)
from investment_agent.portfolio.models import (
    PerformanceComparePoint,
    PerformanceSummary,
    PortfolioSnapshot,
    Position,
    model_name,
)
from investment_agent.universe.constants import BENCHMARK_SYMBOL

DEFAULT_COMPARE_START = date(2026, 7, 1)


def _fetch_price(symbol: str, spy_return_20d: float | None = None) -> PriceMetrics:
    return fetch_price_metrics(symbol, spy_return_20d=spy_return_20d)


def mark_positions(
    positions: list[Position],
    *,
    as_of: date | None = None,
) -> PortfolioSnapshot:
    """Fetch latest prices and attach market value / unrealized P&L to each position."""
    as_of = as_of or analysis_date()
    if not positions:
        return PortfolioSnapshot(
            as_of=as_of,
            positions=[],
            total_cost_basis=0.0,
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
            total_unrealized_pnl_pct=None,
        )

    spy_metrics = _fetch_price(BENCHMARK_SYMBOL)
    spy_20d = spy_metrics.return_20d_pct

    marked: list[Position] = []
    with ThreadPoolExecutor(max_workers=min(6, len(positions))) as pool:
        futures = {
            pool.submit(_fetch_price, p.symbol, spy_20d): p for p in positions
        }
        for fut in as_completed(futures):
            base = futures[fut]
            metrics = fut.result()
            last = metrics.last_close
            cost = base.cost_basis
            if last is not None:
                mkt = base.quantity * last
                unreal = mkt - cost
                unreal_pct = (unreal / cost * 100) if cost else None
            else:
                mkt = None
                unreal = None
                unreal_pct = None
            name = model_name(base).strip() or fetch_symbol_name(base.symbol)
            marked.append(
                base.model_copy(
                    update={
                        "name": name,
                        "last_price": last,
                        "market_value": mkt,
                        "unrealized_pnl": unreal,
                        "unrealized_pnl_pct": unreal_pct,
                    }
                )
            )

    marked.sort(key=lambda p: p.symbol)
    total_cost = sum(p.cost_basis for p in marked)
    total_mkt = sum(p.market_value or 0.0 for p in marked)
    total_unreal = total_mkt - total_cost
    total_unreal_pct = (total_unreal / total_cost * 100) if total_cost else None

    return PortfolioSnapshot(
        as_of=as_of,
        positions=marked,
        total_cost_basis=total_cost,
        total_market_value=total_mkt,
        total_unrealized_pnl=total_unreal,
        total_unrealized_pnl_pct=total_unreal_pct,
    )


def _spy_return_since(start: date, end: date) -> float | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(BENCHMARK_SYMBOL).history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
        )
        if hist.empty or "Close" not in hist.columns:
            return None
        close = hist["Close"].dropna()
        if len(close) < 2:
            return None
        start_px = float(close.iloc[0])
        end_px = float(close.iloc[-1])
        if start_px == 0:
            return None
        return (end_px / start_px - 1) * 100
    except Exception:  # noqa: BLE001
        return None


def _fetch_close_series(symbol: str, start: date, end: date) -> dict[date, float]:
    """Daily adjusted closes for *symbol* in [start, end] inclusive."""
    sym = symbol.strip().upper()
    if not sym:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        return {}

    try:
        hist = yf.Ticker(sym).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
        if hist.empty or "Close" not in hist.columns:
            return {}
        out: dict[date, float] = {}
        for ts, px in hist["Close"].dropna().items():
            out[ts.date()] = float(px)
        return out
    except Exception:  # noqa: BLE001
        return {}


def _price_on_or_before(series: dict[date, float], on_date: date) -> float | None:
    if not series:
        return None
    candidates = [d for d in series if d <= on_date]
    if not candidates:
        return None
    return series[max(candidates)]


def _portfolio_value_on(
    trades: list,
    on_date: date,
    price_maps: dict[str, dict[date, float]],
) -> float:
    active = [t for t in trades if t.trade_date <= on_date]
    positions, _ = compute_positions(active)
    total = 0.0
    for pos in positions:
        px = _price_on_or_before(price_maps.get(pos.symbol, {}), on_date)
        if px is not None:
            total += pos.quantity * px
    return total


def compare_performance_series(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    path: Path | None = None,
) -> list[PerformanceComparePoint]:
    """
    Indexed performance (100 = start) for portfolio MTM vs SPY.

    Portfolio stays at 100 until the first day with holdings, then tracks
    mark-to-market relative to value on that day.
    """
    from_date = from_date or DEFAULT_COMPARE_START
    to_date = to_date or analysis_date()
    if to_date < from_date:
        return []

    db.init_db(path)
    trades = db.fetch_trades(path=path)

    spy_series = _fetch_close_series(BENCHMARK_SYMBOL, from_date, to_date)
    if not spy_series:
        return []

    trading_days = sorted(spy_series)
    spy_base = spy_series[trading_days[0]]

    symbols = sorted({t.symbol for t in trades})
    price_maps: dict[str, dict[date, float]] = {}
    if symbols:
        with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
            futures = {
                pool.submit(_fetch_close_series, sym, from_date, to_date): sym
                for sym in symbols
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                price_maps[sym] = fut.result()

    portfolio_values = [
        _portfolio_value_on(trades, d, price_maps) if trades else 0.0 for d in trading_days
    ]

    first_pos_idx = next((i for i, v in enumerate(portfolio_values) if v > 0), None)
    port_base = portfolio_values[first_pos_idx] if first_pos_idx is not None else None

    points: list[PerformanceComparePoint] = []
    for i, d in enumerate(trading_days):
        spy_index = 100.0 * spy_series[d] / spy_base if spy_base else 100.0
        if port_base is None or portfolio_values[i] <= 0:
            port_index = 100.0
        else:
            port_index = 100.0 * portfolio_values[i] / port_base
        points.append(
            PerformanceComparePoint(
                date=d,
                portfolio_index=port_index,
                spy_index=spy_index,
            )
        )
    return points


def summarize_performance(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    path: Path | None = None,
) -> PerformanceSummary:
    db.init_db(path)
    trades = db.fetch_trades(path=path)
    as_of = to_date or analysis_date()

    positions, _ = compute_positions(trades)
    snapshot = mark_positions(positions, as_of=as_of)

    realized = compute_realized_pnl_in_range(
        trades, from_date=from_date, to_date=to_date
    )
    invested = gross_invested(trades)
    total_pnl = snapshot.total_unrealized_pnl + realized
    total_return_pct = (total_pnl / invested * 100) if invested else None

    first_trade = min((t.trade_date for t in trades), default=None)
    spy_return = None
    vs_spy = None
    if first_trade:
        spy_return = _spy_return_since(first_trade, as_of)
        if spy_return is not None and total_return_pct is not None:
            vs_spy = total_return_pct - spy_return

    return PerformanceSummary(
        as_of=as_of,
        from_date=from_date,
        to_date=to_date,
        snapshot=snapshot,
        realized_pnl=realized,
        total_pnl=total_pnl,
        gross_invested=invested,
        total_return_pct=total_return_pct,
        spy_return_pct=spy_return,
        vs_spy_pct=vs_spy,
        first_trade_date=first_trade,
    )


def get_marked_positions(*, path: Path | None = None) -> PortfolioSnapshot:
    positions = get_open_positions(path=path)
    return mark_positions(positions)
