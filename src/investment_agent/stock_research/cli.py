"""CLI: invest-stock AAPL"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from investment_agent.config import Settings
from investment_agent.llm import QuotaExhaustedError
from investment_agent.stock_research import checkpoint
from investment_agent.stock_research.orchestrator import StockResearchOrchestrator
from investment_agent.stock_research.storage import load_memo, save_run_reports

console = Console()


def _print_memo(memo) -> None:
    title = f"[bold]{memo.ticker}[/bold] · {memo.rating.value.upper()} · conf {memo.confidence:.0%}"
    if memo.company_name:
        title = f"{title} — {memo.company_name}"
    console.print(Panel(memo.executive_summary, title=title, border_style="cyan"))
    if memo.as_of_context:
        console.print(f"[dim]{memo.as_of_context}[/dim]\n")
    console.print(Panel(memo.investment_thesis, title="Thesis", border_style="green"))
    if memo.bull_case:
        console.print("[bold]Bull[/bold]")
        for x in memo.bull_case:
            console.print(f"  + {x}")
    if memo.bear_case:
        console.print("[bold]Bear[/bold]")
        for x in memo.bear_case:
            console.print(f"  - {x}")
    if memo.key_risks:
        console.print("[bold]Risks[/bold]")
        for x in memo.key_risks:
            console.print(f"  ! {x}")
    if memo.data_sources:
        console.print("\n[dim]Sources:[/dim] " + "; ".join(memo.data_sources[:6]))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Single-stock multi-agent research memo")
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--json", action="store_true", help="Print raw JSON memo")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="",
        help="Also write memo JSON to this path",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore checkpoint and run all agents fresh",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load last saved memo for ticker without re-running",
    )
    args = parser.parse_args(argv)
    ticker = args.ticker.strip().upper()

    if args.load:
        memo = load_memo(ticker)
        if memo is None:
            console.print(f"[red]No saved memo for {ticker}[/red]")
            sys.exit(1)
        if args.json:
            console.print_json(memo.model_dump_json())
        else:
            _print_memo(memo)
        return

    try:
        settings = Settings.from_env()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    resume = False if args.no_resume else None
    try:
        memo = StockResearchOrchestrator(settings).run(ticker, resume=resume)
    except QuotaExhaustedError as e:
        console.print(f"[red]{e.user_hint()}[/red]")
        steps = checkpoint.list_checkpoint_steps(ticker)
        if steps:
            console.print(f"[yellow]Checkpoint: {', '.join(steps)}[/yellow]")
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Run failed: {e}[/red]")
        steps = checkpoint.list_checkpoint_steps(ticker)
        if steps:
            console.print(f"[yellow]Partial checkpoint: {', '.join(steps)}[/yellow]")
        sys.exit(1)

    latest, archive = save_run_reports(memo)
    if args.output:
        from pathlib import Path

        from investment_agent.stock_research.storage import save_memo

        save_memo(memo, Path(args.output))

    if args.json:
        console.print_json(memo.model_dump_json())
    else:
        _print_memo(memo)
        console.print(f"\n[dim]Saved {latest} · archive {archive}[/dim]")


def dashboard_main() -> None:
    """Launch unified Streamlit UI (`invest-stock-dashboard` → same as invest-dashboard Stock view)."""
    import subprocess
    from pathlib import Path

    # Prefer unified app; Stock is available under View → Stock.
    app = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app), *sys.argv[1:]],
        check=True,
    )


if __name__ == "__main__":
    main()
