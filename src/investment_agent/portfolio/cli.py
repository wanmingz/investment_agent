"""CLI for portfolio ledger (`invest-portfolio`)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from investment_agent.portfolio.ledger import (
    InsufficientSharesError,
    InvalidDeleteError,
    TradeNotFoundError,
    add_trade,
    delete_trade,
    list_trades,
)
from investment_agent.portfolio.models import TradeInput, TradeSide, model_name
from investment_agent.portfolio.performance import get_marked_positions, summarize_performance

console = Console()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid ISO date: {value!r}") from e


def _cmd_add_trade(args: argparse.Namespace) -> None:
    trade = TradeInput(
        symbol=args.symbol,
        side=TradeSide(args.side),
        quantity=args.quantity,
        price=args.price,
        trade_date=args.date or date.today(),
        name=args.name or "",
        fees=args.fees,
        notes=args.notes or "",
    )
    stored = add_trade(trade, path=args.db)
    label = f"{model_name(stored)} ({stored.symbol})" if model_name(stored) else stored.symbol
    console.print(
        f"[green]Recorded[/green] {stored.side.value} "
        f"{stored.quantity:g} {label} @ ${stored.price:.2f} "
        f"on {stored.trade_date.isoformat()} (id={stored.id})"
    )


def _cmd_delete_trade(args: argparse.Namespace) -> None:
    removed = delete_trade(args.trade_id, path=args.db)
    console.print(
        f"[green]Deleted[/green] trade #{removed.id}: {removed.side.value} "
        f"{removed.quantity:g} {removed.symbol} @ ${removed.price:.2f} "
        f"on {removed.trade_date.isoformat()}"
    )


def _cmd_list_trades(args: argparse.Namespace) -> None:
    trades = list_trades(
        symbol=args.symbol,
        from_date=args.from_date,
        to_date=args.to_date,
        path=args.db,
    )
    if not trades:
        console.print("[dim]No trades found.[/dim]")
        return
    table = Table(title="Trades", show_lines=True)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Date", width=12)
    table.add_column("Side", width=6)
    table.add_column("Symbol", width=8)
    table.add_column("Name", min_width=16)
    table.add_column("Qty", justify="right", width=10)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Fees", justify="right", width=8)
    table.add_column("Notes", min_width=16)
    for t in trades:
        side_style = "green" if t.side == TradeSide.BUY else "red"
        table.add_row(
            str(t.id),
            t.trade_date.isoformat(),
            f"[{side_style}]{t.side.value}[/{side_style}]",
            t.symbol,
            model_name(t) or "—",
            f"{t.quantity:g}",
            f"${t.price:.2f}",
            f"${t.fees:.2f}",
            t.notes[:40] + ("…" if len(t.notes) > 40 else ""),
        )
    console.print(table)


def _cmd_positions(args: argparse.Namespace) -> None:
    snap = get_marked_positions(path=args.db)
    if not snap.positions:
        console.print("[dim]No open positions.[/dim]")
        return
    table = Table(title=f"Open Positions (as of {snap.as_of.isoformat()})", show_lines=True)
    table.add_column("Symbol", width=8)
    table.add_column("Name", min_width=16)
    table.add_column("Qty", justify="right", width=10)
    table.add_column("Avg Cost", justify="right", width=10)
    table.add_column("Last", justify="right", width=10)
    table.add_column("Mkt Value", justify="right", width=12)
    table.add_column("Unreal P&L", justify="right", width=12)
    table.add_column("Unreal %", justify="right", width=10)
    for p in snap.positions:
        unreal_style = ""
        if p.unrealized_pnl is not None:
            unreal_style = "green" if p.unrealized_pnl >= 0 else "red"
        table.add_row(
            p.symbol,
            model_name(p) or "—",
            f"{p.quantity:g}",
            f"${p.avg_cost:.2f}",
            f"${p.last_price:.2f}" if p.last_price is not None else "—",
            f"${p.market_value:,.2f}" if p.market_value is not None else "—",
            f"[{unreal_style}]${p.unrealized_pnl:,.2f}[/{unreal_style}]"
            if p.unrealized_pnl is not None
            else "—",
            f"{p.unrealized_pnl_pct:.1f}%" if p.unrealized_pnl_pct is not None else "—",
        )
    console.print(table)
    console.print(
        f"\n[bold]Total[/bold] cost ${snap.total_cost_basis:,.2f} · "
        f"holdings ${snap.total_market_value:,.2f} · "
        f"cash ${snap.cash_balance:,.2f} · "
        f"NAV ${snap.total_nav:,.2f} · "
        f"unrealized ${snap.total_unrealized_pnl:,.2f}"
        + (f" ({snap.total_unrealized_pnl_pct:.1f}%)" if snap.total_unrealized_pnl_pct is not None else "")
    )


def _cmd_performance(args: argparse.Namespace) -> None:
    summary = summarize_performance(
        from_date=args.from_date,
        to_date=args.to_date,
        path=args.db,
    )
    if not summary.first_trade_date:
        console.print("[dim]No trades recorded yet.[/dim]")
        return

    period = ""
    if args.from_date or args.to_date:
        f = args.from_date.isoformat() if args.from_date else "…"
        t = args.to_date.isoformat() if args.to_date else summary.as_of.isoformat()
        period = f" ({f} → {t})"

    console.print(f"[bold]Performance{period}[/bold] · as of {summary.as_of.isoformat()}")
    console.print(f"  Portfolio value: ${summary.snapshot.total_nav:,.2f}")
    console.print(f"  Net invested:    ${summary.gross_invested:,.2f}")
    console.print(f"  Realized P&L:    ${summary.realized_pnl:,.2f}")
    console.print(f"  Unrealized P&L:  ${summary.snapshot.total_unrealized_pnl:,.2f}")
    console.print(f"  Total P&L:       ${summary.total_pnl:,.2f}")
    if summary.total_return_pct is not None:
        console.print(f"  Total return:    {summary.total_return_pct:.2f}%")
    if summary.spy_return_pct is not None:
        console.print(
            f"  SPY return:      {summary.spy_return_pct:.2f}% "
            f"(since {summary.first_trade_date.isoformat()})"
        )
    if summary.vs_spy_pct is not None:
        style = "green" if summary.vs_spy_pct >= 0 else "red"
        console.print(f"  vs SPY:          [{style}]{summary.vs_spy_pct:+.2f} pp[/{style}]")

    if summary.snapshot.positions:
        console.print()
        _cmd_positions(argparse.Namespace(db=args.db))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Portfolio ledger — record trades, view positions and performance"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Portfolio SQLite path (default: reports/portfolio.db or PORTFOLIO_DB_PATH)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-trade", help="Record a buy or sell trade")
    p_add.add_argument("symbol", help="Ticker symbol (e.g. AAPL)")
    p_add.add_argument("side", choices=["buy", "sell"])
    p_add.add_argument("quantity", type=float, help="Share quantity")
    p_add.add_argument("price", type=float, help="Price per share")
    p_add.add_argument("--date", type=_parse_date, help="Trade date (YYYY-MM-DD, default today)")
    p_add.add_argument("--name", default="", help="Display name (auto-fetched if omitted)")
    p_add.add_argument("--fees", type=float, default=0.0, help="Fees/commission")
    p_add.add_argument("--notes", default="", help="Optional note")
    p_add.set_defaults(func=_cmd_add_trade)

    p_del = sub.add_parser("delete-trade", help="Delete a trade by id")
    p_del.add_argument("trade_id", type=int, help="Trade id from list-trades")
    p_del.set_defaults(func=_cmd_delete_trade)

    p_list = sub.add_parser("list-trades", help="List recorded trades")
    p_list.add_argument("--symbol", default=None, help="Filter by symbol")
    p_list.add_argument("--from", dest="from_date", type=_parse_date, help="From date")
    p_list.add_argument("--to", dest="to_date", type=_parse_date, help="To date")
    p_list.set_defaults(func=_cmd_list_trades)

    p_pos = sub.add_parser("positions", help="Show open positions with mark-to-market")
    p_pos.set_defaults(func=_cmd_positions)

    p_perf = sub.add_parser("performance", help="Portfolio performance summary")
    p_perf.add_argument("--from", dest="from_date", type=_parse_date, help="Realized P&L from date")
    p_perf.add_argument("--to", dest="to_date", type=_parse_date, help="As-of / to date")
    p_perf.set_defaults(func=_cmd_performance)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except InsufficientSharesError as e:
        console.print(f"[red]Insufficient shares:[/red] {e}")
        sys.exit(1)
    except TradeNotFoundError as e:
        console.print(f"[red]Not found:[/red] {e}")
        sys.exit(1)
    except InvalidDeleteError as e:
        console.print(f"[red]Cannot delete:[/red] {e}")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid input:[/red] {e}")
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"[red]Database error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
