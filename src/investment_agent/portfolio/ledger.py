"""Trade ledger and position derivation (weighted average cost)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from investment_agent.portfolio.quotes import fetch_symbol_name
from investment_agent.portfolio import db
from investment_agent.portfolio.db import LedgerKind, resolve_db_path
from investment_agent.portfolio.models import Position, Trade, TradeInput, TradeSide, model_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LedgerState:
    """Cash balance and open share quantities after replaying trades."""

    cash: float
    holdings: dict[str, float]


def _buy_shortfall(cash: float, cost: float) -> tuple[float, float]:
    """Return (new_cash, external_deposit) after funding a buy from cash first."""
    shortfall = max(0.0, cost - cash)
    return cash + shortfall - cost, shortfall


def replay_ledger_to(trades: list[Trade], on_date: date) -> LedgerState:
    """Replay trades through *on_date* (inclusive): cash + share quantities."""
    cash = 0.0
    holdings: dict[str, float] = {}
    active = sorted(
        (t for t in trades if t.trade_date <= on_date),
        key=lambda t: (t.trade_date, t.id),
    )
    for trade in active:
        sym = trade.symbol
        if trade.side == TradeSide.BUY:
            cost = trade.quantity * trade.price + trade.fees
            cash, _ = _buy_shortfall(cash, cost)
            holdings[sym] = holdings.get(sym, 0.0) + trade.quantity
        else:
            proceeds = trade.quantity * trade.price - trade.fees
            holdings[sym] = holdings.get(sym, 0.0) - trade.quantity
            if holdings[sym] <= 1e-9:
                holdings.pop(sym, None)
            cash += proceeds
    return LedgerState(cash=cash, holdings=holdings)


def external_inflow_on_date(trades: list[Trade], on_date: date) -> float:
    """New capital required on *on_date* (buys not fully covered by cash on hand)."""
    cash = 0.0
    holdings: dict[str, float] = {}
    flow = 0.0
    active = sorted(
        (t for t in trades if t.trade_date <= on_date),
        key=lambda t: (t.trade_date, t.id),
    )
    for trade in active:
        sym = trade.symbol
        if trade.side == TradeSide.BUY:
            cost = trade.quantity * trade.price + trade.fees
            shortfall = max(0.0, cost - cash)
            if trade.trade_date == on_date:
                flow += shortfall
            cash, _ = _buy_shortfall(cash, cost)
            holdings[sym] = holdings.get(sym, 0.0) + trade.quantity
        else:
            proceeds = trade.quantity * trade.price - trade.fees
            holdings[sym] = holdings.get(sym, 0.0) - trade.quantity
            if holdings[sym] <= 1e-9:
                holdings.pop(sym, None)
            cash += proceeds
    return flow


def net_external_contributions(trades: list[Trade], *, through: date | None = None) -> float:
    """Cumulative external capital deposited to fund buys (sells stay in cash)."""
    if not trades:
        return 0.0
    end = through or max(t.trade_date for t in trades)
    cash = 0.0
    total = 0.0
    for trade in sorted(
        (t for t in trades if t.trade_date <= end),
        key=lambda t: (t.trade_date, t.id),
    ):
        if trade.side == TradeSide.BUY:
            cost = trade.quantity * trade.price + trade.fees
            shortfall = max(0.0, cost - cash)
            total += shortfall
            cash, _ = _buy_shortfall(cash, cost)
        else:
            cash += trade.quantity * trade.price - trade.fees
    return total


class InsufficientSharesError(ValueError):
    """Sell quantity exceeds open position."""


class TradeNotFoundError(ValueError):
    """Trade id does not exist."""


class InvalidDeleteError(ValueError):
    """Deleting this trade would leave the ledger inconsistent."""


def compute_positions(trades: list[Trade]) -> tuple[list[Position], float]:
    """
    Derive open positions and cumulative realized P&L from trade history.

    Returns (open_positions, total_realized_pnl).
    """
    sorted_trades = sorted(trades, key=lambda t: (t.trade_date, t.id))
    holdings: dict[str, tuple[float, float, str]] = {}  # symbol -> (shares, avg_cost, name)
    realized_pnl = 0.0

    for trade in sorted_trades:
        sym = trade.symbol
        shares, avg_cost, name = holdings.get(sym, (0.0, 0.0, ""))
        if model_name(trade):
            name = model_name(trade)

        if trade.side == TradeSide.BUY:
            buy_cost = trade.quantity * trade.price + trade.fees
            new_shares = shares + trade.quantity
            if new_shares > 0:
                new_avg = (shares * avg_cost + buy_cost) / new_shares
                holdings[sym] = (new_shares, new_avg, name)
        else:
            if trade.quantity > shares + 1e-9:
                raise InsufficientSharesError(
                    f"Cannot sell {trade.quantity} {sym}: only {shares} shares held"
                )
            proceeds = trade.quantity * trade.price - trade.fees
            cost_removed = trade.quantity * avg_cost
            realized_pnl += proceeds - cost_removed
            new_shares = shares - trade.quantity
            if new_shares > 1e-9:
                holdings[sym] = (new_shares, avg_cost, name)
            elif sym in holdings:
                del holdings[sym]

    positions: list[Position] = []
    for sym in sorted(holdings):
        qty, avg, name = holdings[sym]
        if qty <= 1e-9:
            continue
        positions.append(
            Position(
                symbol=sym,
                name=name,
                quantity=qty,
                avg_cost=avg,
                cost_basis=qty * avg,
            )
        )
    return positions, realized_pnl


def compute_realized_pnl_in_range(
    trades: list[Trade],
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> float:
    """Realized P&L from sells within [from_date, to_date] (inclusive)."""
    if not from_date and not to_date:
        _, total = compute_positions(trades)
        return total

    sorted_trades = sorted(trades, key=lambda t: (t.trade_date, t.id))
    holdings: dict[str, tuple[float, float]] = {}
    realized = 0.0

    for trade in sorted_trades:
        sym = trade.symbol
        shares, avg_cost = holdings.get(sym, (0.0, 0.0))

        if trade.side == TradeSide.BUY:
            buy_cost = trade.quantity * trade.price + trade.fees
            new_shares = shares + trade.quantity
            if new_shares > 0:
                holdings[sym] = (new_shares, (shares * avg_cost + buy_cost) / new_shares)
        else:
            if trade.quantity > shares + 1e-9:
                raise InsufficientSharesError(
                    f"Cannot sell {trade.quantity} {sym}: only {shares} shares held"
                )
            in_range = True
            if from_date and trade.trade_date < from_date:
                in_range = False
            if to_date and trade.trade_date > to_date:
                in_range = False
            if in_range:
                proceeds = trade.quantity * trade.price - trade.fees
                realized += proceeds - trade.quantity * avg_cost
            new_shares = shares - trade.quantity
            if new_shares > 1e-9:
                holdings[sym] = (new_shares, avg_cost)
            elif sym in holdings:
                del holdings[sym]

    return realized


def gross_invested(trades: list[Trade]) -> float:
    """Total capital deployed on buys (notional + fees)."""
    total = 0.0
    for t in trades:
        if t.side == TradeSide.BUY:
            total += t.quantity * t.price + t.fees
    return total


def add_trade(
    trade: TradeInput,
    *,
    path: Path | None = None,
    ledger: LedgerKind = "manual",
) -> Trade:
    """Validate sell against current holdings, persist, and return the stored trade."""
    target = resolve_db_path(path, ledger)
    existing = db.fetch_trades(path=target)
    if trade.side == TradeSide.SELL:
        positions, _ = compute_positions(existing)
        held = next((p.quantity for p in positions if p.symbol == trade.symbol), 0.0)
        if trade.quantity > held + 1e-9:
            raise InsufficientSharesError(
                f"Cannot sell {trade.quantity} {trade.symbol}: only {held} shares held"
            )

    payload = trade
    if not model_name(trade).strip():
        name = fetch_symbol_name(trade.symbol)
        if not name:
            open_positions, _ = compute_positions(existing)
            pos = next((p for p in open_positions if p.symbol == trade.symbol), None)
            name = model_name(pos) if pos else ""
        if name:
            payload = trade.model_copy(update={"name": name})

    stored = db.insert_trade(payload, path=target)
    logger.info(
        "Trade recorded: %s %s %.4g @ %.4f on %s",
        stored.side.value,
        stored.symbol,
        stored.quantity,
        stored.price,
        stored.trade_date.isoformat(),
    )
    return stored


def delete_trade(
    trade_id: int,
    *,
    path: Path | None = None,
    ledger: LedgerKind = "manual",
) -> Trade:
    """Remove a trade after verifying the remaining history stays valid."""
    target = resolve_db_path(path, ledger)
    existing = db.fetch_trade_by_id(trade_id, path=target)
    if existing is None:
        raise TradeNotFoundError(f"Trade id={trade_id} not found")

    remaining = [t for t in db.fetch_trades(path=target) if t.id != trade_id]
    try:
        compute_positions(remaining)
    except InsufficientSharesError as e:
        raise InvalidDeleteError(
            f"Cannot delete trade #{trade_id}: remaining history would be invalid ({e})"
        ) from e

    if not db.delete_trade_by_id(trade_id, path=target):
        raise TradeNotFoundError(f"Trade id={trade_id} not found")

    logger.info(
        "Trade deleted: id=%s %s %s %.4g @ %.4f on %s",
        existing.id,
        existing.side.value,
        existing.symbol,
        existing.quantity,
        existing.price,
        existing.trade_date.isoformat(),
    )
    return existing


def list_trades(
    *,
    symbol: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    path: Path | None = None,
    ledger: LedgerKind = "manual",
) -> list[Trade]:
    target = resolve_db_path(path, ledger)
    return db.fetch_trades(
        symbol=symbol, from_date=from_date, to_date=to_date, path=target
    )


def get_open_positions(
    *,
    path: Path | None = None,
    ledger: LedgerKind = "manual",
) -> list[Position]:
    target = resolve_db_path(path, ledger)
    trades = db.fetch_trades(path=target)
    positions, _ = compute_positions(trades)
    return positions
