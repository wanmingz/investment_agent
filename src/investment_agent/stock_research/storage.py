"""Persist InvestmentMemo under reports/stock_research/ (and published brief/)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from investment_agent.stock_research.models import InvestmentMemo

_REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = _REPO_ROOT / "reports" / "stock_research"
RUNS_DIR = REPORT_DIR / "runs"
BRIEF_DIR = _REPO_ROOT / "brief"


def latest_path(ticker: str) -> Path:
    return REPORT_DIR / f"{ticker.strip().upper()}_latest.json"


def published_path(ticker: str) -> Path:
    """Tracked Cloud-readable path: brief/stock_{TICKER}_latest.json."""
    return BRIEF_DIR / f"stock_{ticker.strip().upper()}_latest.json"


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
    """Load local reports/ memo; fall back to published brief/stock_* for Cloud."""
    if path is not None:
        target = path
    elif ticker:
        local = latest_path(ticker)
        if local.is_file():
            target = local
        else:
            target = published_path(ticker)
    else:
        # newest local *_latest.json if any, else newest published
        target = None
        if REPORT_DIR.is_dir():
            candidates = sorted(
                REPORT_DIR.glob("*_latest.json"), key=lambda p: p.stat().st_mtime
            )
            if candidates:
                target = candidates[-1]
        if target is None and BRIEF_DIR.is_dir():
            published = sorted(
                BRIEF_DIR.glob("stock_*_latest.json"),
                key=lambda p: p.stat().st_mtime,
            )
            if published:
                target = published[-1]
        if target is None:
            return None
    if not target.is_file():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return InvestmentMemo.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None


def list_latest_tickers() -> list[str]:
    """Tickers with a local or published memo (local wins for duplicates)."""
    found: set[str] = set()
    if REPORT_DIR.is_dir():
        for p in REPORT_DIR.glob("*_latest.json"):
            name = p.name.removesuffix("_latest.json")
            if name:
                found.add(name)
    if BRIEF_DIR.is_dir():
        for p in BRIEF_DIR.glob("stock_*_latest.json"):
            # stock_AAPL_latest.json → AAPL
            mid = p.name.removeprefix("stock_").removesuffix("_latest.json")
            if mid:
                found.add(mid)
    return sorted(found)
