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
    external_inflow_on_date,
    net_external_contributions,
    replay_ledger_to,
)
from investment_agent.portfolio.models import (
    PerformanceComparePoint,
    PerformanceSummary,
    PortfolioSnapshot,
    Position,
    Trade,
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
    trades: list[Trade] | None = None,
) -> PortfolioSnapshot:
    """Fetch latest prices and attach market value / unrealized P&L to each position."""
    as_of = as_of or analysis_date()
    if not positions:
        cash = replay_ledger_to(trades, as_of).cash if trades else 0.0
        return PortfolioSnapshot(
            as_of=as_of,
            positions=[],
            total_cost_basis=0.0,
            total_market_value=0.0,
            cash_balance=cash,
            total_nav=cash,
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
    cash = replay_ledger_to(trades, as_of).cash if trades else 0.0
    total_nav = cash + total_mkt

    return PortfolioSnapshot(
        as_of=as_of,
        positions=marked,
        total_cost_basis=total_cost,
        total_market_value=total_mkt,
        cash_balance=cash,
        total_nav=total_nav,
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


def _portfolio_nav_on(
    trades: list[Trade],
    on_date: date,
    price_maps: dict[str, dict[date, float]],
) -> float:
    """Cash + mark-to-market holdings at end of *on_date* (trades applied in order)."""
    state = replay_ledger_to(trades, on_date)
    nav = state.cash
    for sym, qty in state.holdings.items():
        px = _price_on_or_before(price_maps.get(sym, {}), on_date)
        if px is not None:
            nav += qty * px
    return nav


def _external_flow_on_date(trades: list[Trade], on_date: date) -> float:
    """Capital added on *on_date* when buys exceed cash on hand."""
    return external_inflow_on_date(trades, on_date)


def compare_performance_series(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    path: Path | None = None,
) -> list[PerformanceComparePoint]:
    """
    Chain-linked indexed performance (100 = portfolio start) vs SPY.

    Portfolio NAV = cash from sells + mark-to-market holdings. Daily returns
    adjust for buy inflows so new capital is not counted as performance.
    SPY is rebased to 100 on the same day the portfolio index starts.
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

    navs = [
        _portfolio_nav_on(trades, d, price_maps) if trades else 0.0 for d in trading_days
    ]
    flows = [_external_flow_on_date(trades, d) for d in trading_days]

    first_nav_idx = next((i for i, nav in enumerate(navs) if nav > 0), None)
    if first_nav_idx is None:
        spy_base = spy_series[trading_days[0]]
        return [
            PerformanceComparePoint(
                date=d,
                portfolio_index=100.0,
                spy_index=100.0 * spy_series[d] / spy_base if spy_base else 100.0,
            )
            for d in trading_days
        ]

    spy_base_day = trading_days[first_nav_idx]
    spy_base = spy_series[spy_base_day]

    port_index = 100.0
    prev_nav = navs[first_nav_idx]

    points: list[PerformanceComparePoint] = []
    for i, d in enumerate(trading_days):
        spy_index = 100.0 * spy_series[d] / spy_base if spy_base else 100.0

        if i < first_nav_idx:
            port_index_out = 100.0
        elif i == first_nav_idx:
            port_index_out = 100.0
            prev_nav = navs[i]
        else:
            nav = navs[i]
            flow = flows[i]
            denominator = prev_nav + flow
            if denominator > 0:
                port_index *= nav / denominator
            if nav > 0:
                prev_nav = nav
            port_index_out = port_index

        points.append(
            PerformanceComparePoint(
                date=d,
                portfolio_index=port_index_out,
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
    snapshot = mark_positions(positions, as_of=as_of, trades=trades)

    realized = compute_realized_pnl_in_range(
        trades, from_date=from_date, to_date=to_date
    )
    invested = net_external_contributions(trades, through=as_of)
    total_pnl = snapshot.total_nav - invested
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
    trades = db.fetch_trades(path=path)
    positions, _ = compute_positions(trades)
    return mark_positions(positions, trades=trades)
