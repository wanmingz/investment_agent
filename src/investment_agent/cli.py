import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from investment_agent.brief_compat import (
    brief_data_sources,
    brief_news_citations,
    brief_news_view,
    theme_drivers_sourced,
    theme_risks_sourced,
)
from investment_agent.config import Settings
from investment_agent.models import stage_label
from investment_agent import checkpoint
from investment_agent.errors import QuotaExhaustedError
from investment_agent.orchestrator import ThemeOrchestrator
from investment_agent.storage import save_brief

console = Console()


def _stage_style(stage: str) -> str:
    return {
        "early": "bold green",
        "early_mid": "green",
        "mid": "bold yellow",
        "mid_late": "yellow",
        "late": "bold red",
    }.get(stage, "white")


def _theme_display_name(t) -> str:
    return t.subtitle or t.name


def print_brief(brief) -> None:
    date_line = ""
    if brief.as_of_context.lower().startswith("as of"):
        date_line = brief.as_of_context.split("·")[0].strip()
    elif brief.report_date:
        date_line = f"As of {brief.report_date}"
    title = "[bold]Investment Theme Brief[/bold]"
    if date_line:
        title = f"{title} · {date_line}"
    console.print(Panel(brief.executive_summary, title=title, border_style="cyan"))
    if brief.as_of_context and "·" in brief.as_of_context:
        console.print(f"[dim]{brief.as_of_context}[/dim]\n")

    views = [
        ("Regime", brief.macro_view),
        ("Narrative", brief_news_view(brief) or "—"),
        ("Markets (equity)", brief.equity_view),
        ("Markets (quant)", brief.quant_view),
    ]
    for view_title, text in views:
        console.print(Panel(text, title=view_title, border_style="dim"))

    table = Table(title="Recommended Investment Themes", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Theme", min_width=18)
    table.add_column("Stage", justify="center", width=10)
    table.add_column("Investability", justify="right", width=12)
    table.add_column("Consensus", justify="right", width=8)
    table.add_column("Agent Stages", min_width=22)
    table.add_column("Summary", min_width=36)

    for i, t in enumerate(brief.themes, 1):
        stages = " | ".join(
            f"{k[:3]}:{v.value}" for k, v in t.agent_stages.items()
        )
        stage_val = t.stage.value if hasattr(t.stage, "value") else str(t.stage)
        label = t.stage_label or stage_label(t.stage)
        table.add_row(
            str(i),
            f"{_theme_display_name(t)}\n[dim]{t.name}[/dim]",
            f"[{_stage_style(stage_val)}]{label}[/{_stage_style(stage_val)}]",
            f"{t.investability_score:.0%}",
            f"{t.consensus_score:.0%}",
            stages,
            t.synthesis[:120] + ("…" if len(t.synthesis) > 120 else ""),
        )
    console.print(table)

    sources = brief_data_sources(brief)
    if sources:
        console.print("[dim]Data sources:[/dim] " + "; ".join(sources))

    cite_by_id = {c.id: c for c in brief_news_citations(brief)}

    for i, t in enumerate(brief.themes, 1):
        drivers = "\n".join(f"  • {d}" for d in t.key_drivers[:4])
        risks = "\n".join(f"  • {r}" for r in t.risks[:3])
        src_drv = []
        for item in theme_drivers_sourced(t):
            refs = ", ".join(
                cite_by_id[cid].title[:40] if cid in cite_by_id else cid
                for cid in item.citation_ids
            )
            src_drv.append(f"  • {item.text} [news: {refs}]")
        src_risk = []
        for item in theme_risks_sourced(t):
            refs = ", ".join(
                cite_by_id[cid].title[:40] if cid in cite_by_id else cid
                for cid in item.citation_ids
            )
            src_risk.append(f"  • {item.text} [news: {refs}]")
        tickers = ", ".join(t.tickers_or_sectors[:6])
        label = t.stage_label or stage_label(t.stage)
        console.print(
            Panel(
                f"{t.thesis}\n\n"
                f"[bold]Key drivers[/bold]\n{drivers or '  —'}\n\n"
                f"[bold]Key drivers (news-sourced)[/bold]\n"
                f"{chr(10).join(src_drv) if src_drv else '  —'}\n\n"
                f"[bold]Risks[/bold]\n{risks or '  —'}\n\n"
                f"[bold]Risks (news-sourced)[/bold]\n"
                f"{chr(10).join(src_risk) if src_risk else '  —'}\n\n"
                f"[bold]Tickers / sectors[/bold] {tickers or '—'}",
                title=f"#{i} {_theme_display_name(t)} · {label}",
                border_style=_stage_style(
                    t.stage.value if hasattr(t.stage, "value") else str(t.stage)
                ),
            )
        )

    console.print(f"\n[dim]{brief.disclaimer}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent investment theme analyzer (Regime + Narrative + Markets)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Market region override (e.g. US, China, global)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Save JSON report to file (e.g. reports/latest.json)",
    )
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        if args.region:
            from dataclasses import replace

            settings = replace(settings, market_region=args.region)

        console.print("[bold]Running 3-agent analysis (v2)…[/bold]")
        console.print(f"  Model: {settings.provider} / {settings.model}")
        console.print("  Regime agent")
        console.print("  Narrative agent (news RAG)")
        console.print("  Markets agent (fundamentals + vol)\n")

        orchestrator = ThemeOrchestrator(settings)
        brief = orchestrator.run()

        if args.output is not None:
            out_path = save_brief(brief, args.output)
            console.print(f"[green]Report saved:[/green] {out_path}")

        if args.json:
            print(brief.model_dump_json(indent=2, ensure_ascii=False))
        else:
            print_brief(brief)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)
    except QuotaExhaustedError as e:
        console.print(f"[red]API quota exceeded:[/red]\n{e.user_hint()}")
        steps = checkpoint.list_checkpoint_steps()
        if steps:
            console.print(f"[yellow]Checkpoint saved:[/yellow] {', '.join(steps)}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Run failed:[/red] {e}")
        steps = checkpoint.list_checkpoint_steps()
        if steps:
            console.print(
                f"[yellow]Partial checkpoint:[/yellow] {', '.join(steps)} — rerun with RESUME_CHECKPOINT=1"
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
