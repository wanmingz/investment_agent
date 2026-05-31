import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pathlib import Path

from investment_agent.config import Settings
from investment_agent.orchestrator import STAGE_ZH, ThemeOrchestrator
from investment_agent.storage import save_brief

console = Console()


def _stage_style(stage: str) -> str:
    return {
        "early": "bold green",
        "mid": "bold yellow",
        "late": "bold red",
    }.get(stage, "white")


def print_brief(brief) -> None:
    console.print(
        Panel(brief.executive_summary, title="[bold]投资主题简报[/bold]", border_style="cyan")
    )

    views = [
        ("宏观 (Agent 1)", brief.macro_view),
        ("股票 (Agent 2)", brief.equity_view),
        ("量化波动 (Agent 3)", brief.quant_view),
    ]
    for title, text in views:
        console.print(Panel(text, title=title, border_style="dim"))

    table = Table(title="当前推荐投资主题", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("主题", min_width=18)
    table.add_column("阶段", justify="center", width=8)
    table.add_column("可投资性", justify="right", width=8)
    table.add_column("共识度", justify="right", width=6)
    table.add_column("三 Agent 阶段", min_width=22)
    table.add_column("逻辑摘要", min_width=36)

    for i, t in enumerate(brief.themes, 1):
        stages = " | ".join(
            f"{k[:3]}:{v.value}" for k, v in t.agent_stages.items()
        )
        stage_val = t.stage.value if hasattr(t.stage, "value") else str(t.stage)
        table.add_row(
            str(i),
            f"{t.name_zh or t.name}\n[dim]{t.name}[/dim]",
            f"[{_stage_style(stage_val)}]{t.stage_label_zh}[/{_stage_style(stage_val)}]",
            f"{t.investability_score:.0%}",
            f"{t.consensus_score:.0%}",
            stages,
            t.synthesis[:120] + ("…" if len(t.synthesis) > 120 else ""),
        )
    console.print(table)

    for i, t in enumerate(brief.themes, 1):
        drivers = "\n".join(f"  • {d}" for d in t.key_drivers[:4])
        risks = "\n".join(f"  • {r}" for r in t.risks[:3])
        tickers = ", ".join(t.tickers_or_sectors[:6])
        console.print(
            Panel(
                f"{t.thesis}\n\n"
                f"[bold]驱动因素[/bold]\n{drivers or '  —'}\n\n"
                f"[bold]风险[/bold]\n{risks or '  —'}\n\n"
                f"[bold]标的/板块[/bold] {tickers or '—'}",
                title=f"#{i} {t.name_zh or t.name} · {STAGE_ZH.get(t.stage, t.stage_label_zh)}",
                border_style=_stage_style(
                    t.stage.value if hasattr(t.stage, "value") else str(t.stage)
                ),
            )
        )

    console.print(f"\n[dim]{brief.disclaimer}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent investment theme analyzer (Macro + Equity + Quant)"
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
        help="Save JSON report to file (default: reports/latest.json when set alone)",
    )
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        if args.region:
            from dataclasses import replace

            settings = replace(settings, market_region=args.region)

        console.print("[bold]启动三 Agent 分析…[/bold]")
        console.print(f"  模型: {settings.provider} / {settings.model}")
        console.print("  Agent 1: 宏观经济学家")
        console.print("  Agent 2: 股票研究员")
        console.print("  Agent 3: 量化波动分析师\n")

        orchestrator = ThemeOrchestrator(settings)
        brief = orchestrator.run()

        if args.output is not None:
            out_path = save_brief(brief, args.output)
            console.print(f"[green]已保存报告:[/green] {out_path}")

        if args.json:
            print(brief.model_dump_json(indent=2, ensure_ascii=False))
        else:
            print_brief(brief)
    except ValueError as e:
        console.print(f"[red]配置错误:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]运行失败:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
