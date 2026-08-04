"""Persist InvestmentMemo under reports/stock_research/."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from investment_agent.stock_research.models import InvestmentMemo

REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "stock_research"
RUNS_DIR = REPORT_DIR / "runs"


def latest_path(ticker: str) -> Path:
    return REPORT_DIR / f"{ticker.strip().upper()}_latest.json"


def run_archive_path(ticker: str, *, now: datetime | None = None) -> Path:
    now = now or datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    return RUNS_DIR / f"{ticker.strip().upper()}_{stamp}.json"


def save_memo(memo: InvestmentMemo, path: Path | None = None) -> Path:
    target = path or latest_path(memo.ticker)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        memo.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def save_run_reports(memo: InvestmentMemo) -> tuple[Path, Path]:
    latest = save_memo(memo)
    archive = save_memo(memo, run_archive_path(memo.ticker))
    return latest, archive


def load_memo(ticker: str | None = None, path: Path | None = None) -> InvestmentMemo | None:
    if path is not None:
        target = path
    elif ticker:
        target = latest_path(ticker)
    else:
        # newest *_latest.json if any
        if not REPORT_DIR.is_dir():
            return None
        candidates = sorted(REPORT_DIR.glob("*_latest.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return None
        target = candidates[-1]
    if not target.is_file():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return InvestmentMemo.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None


def list_latest_tickers() -> list[str]:
    if not REPORT_DIR.is_dir():
        return []
    out: list[str] = []
    for p in sorted(REPORT_DIR.glob("*_latest.json")):
        name = p.name.removesuffix("_latest.json")
        if name:
            out.append(name)
    return out
