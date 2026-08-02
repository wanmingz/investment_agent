"""Persist InvestmentBrief + safe accessors for schema versions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from investment_agent.dates import analysis_date, build_as_of_context, format_date_iso
from investment_agent.models import (
    FinalTheme,
    InvestmentBrief,
    NewsCitation,
    SourcedItem,
)

DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "latest.json"
PUBLISHED_BRIEF_PATH = Path(__file__).resolve().parents[2] / "brief" / "latest.json"
RUNS_DIR = DEFAULT_REPORT_PATH.parent / "runs"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def brief_narrative_view(brief: InvestmentBrief) -> str:
    return _get(brief, "narrative_view", "") or ""


def brief_data_sources(brief: InvestmentBrief) -> list[str]:
    val = _get(brief, "data_sources", None)
    return list(val) if val else []


def brief_agent_themes(brief: InvestmentBrief, agent: str) -> list:
    key = f"{agent}_themes"
    val = _get(brief, key, None)
    return list(val) if val else []


def brief_fundamentals_notes(brief: InvestmentBrief) -> list[str]:
    val = _get(brief, "fundamentals_notes", None)
    return list(val) if val else []


def brief_narrative_citations(brief: InvestmentBrief) -> list[NewsCitation]:
    val = _get(brief, "narrative_citations", None)
    return list(val) if val else []


def theme_drivers_sourced(theme: FinalTheme) -> list[SourcedItem]:
    val = _get(theme, "key_drivers_sourced", None)
    return list(val) if val else []


def theme_risks_sourced(theme: FinalTheme) -> list[SourcedItem]:
    val = _get(theme, "risks_sourced", None)
    return list(val) if val else []


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _normalize_theme_dict(theme: dict) -> None:
    """Prefer English theme name for display; drop legacy name_zh subtitles."""
    if not isinstance(theme, dict):
        return
    sub = str(theme.get("subtitle") or theme.pop("name_zh", "") or "").strip()
    name = str(theme.get("name") or "").strip()
    if sub and _has_cjk(sub) and name and not _has_cjk(name):
        theme["subtitle"] = ""
    elif name and _has_cjk(name) and sub and not _has_cjk(sub):
        theme["name"], theme["subtitle"] = sub, ""
    elif sub:
        theme["subtitle"] = sub
    theme.pop("name_zh", None)
    if theme.get("stage_label_zh") and not theme.get("stage_label"):
        theme["stage_label"] = theme.pop("stage_label_zh")
    else:
        theme.pop("stage_label_zh", None)


def normalize_brief_dict(data: dict) -> dict:
    """Fill optional v2 keys and normalize theme display fields when loading JSON."""
    data.setdefault("regime_view", "")
    data.setdefault("narrative_view", "")
    data.setdefault("markets_fundamentals_view", "")
    data.setdefault("markets_vol_view", "")
    data.setdefault("narrative_citations", [])
    data.setdefault("data_sources", [])
    data.setdefault("fundamentals_notes", [])
    data.setdefault("regime_themes", [])
    data.setdefault("narrative_themes", [])
    data.setdefault("markets_themes", [])

    for key in ("regime_themes", "narrative_themes", "markets_themes"):
        for theme in data.get(key, []):
            if isinstance(theme, dict):
                _normalize_theme_dict(theme)

    for theme in data.get("themes", []):
        if not isinstance(theme, dict):
            continue
        _normalize_theme_dict(theme)
        theme.setdefault("key_drivers_sourced", [])
        theme.setdefault("risks_sourced", [])
        theme.setdefault("contributing_agents", [])
        theme.setdefault("primary_agent", "")
        theme.setdefault("agent_stages", {})

    return data


def run_archive_path(brief: InvestmentBrief, *, now: datetime | None = None) -> Path:
    """Timestamped path under reports/runs/ (multiple runs per calendar day)."""
    now = now or datetime.now()
    date_part = brief.report_date or format_date_iso(analysis_date())
    stamp = now.strftime("%H%M%S")
    return RUNS_DIR / f"{date_part}_{stamp}.json"


def save_brief(brief: InvestmentBrief, path: Path | None = None) -> Path:
    target = path or DEFAULT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        brief.model_dump_json(indent=2, ensure_ascii=False, by_alias=False),
        encoding="utf-8",
    )
    return target


def save_run_reports(brief: InvestmentBrief) -> tuple[Path, Path]:
    """Persist latest.json and a timestamped archive copy for this run."""
    latest = save_brief(brief)
    archive = save_brief(brief, run_archive_path(brief))
    return latest, archive


def list_run_reports(*, limit: int = 50) -> list[Path]:
    """Newest-first paths under reports/runs/."""
    if not RUNS_DIR.is_dir():
        return []
    files = sorted(RUNS_DIR.glob("*.json"), reverse=True)
    return files[:limit]


def resolve_brief_path(path: Path | None = None) -> Path | None:
    """Prefer local reports/latest.json; fall back to published brief/latest.json."""
    if path is not None:
        return path if path.is_file() else None
    if DEFAULT_REPORT_PATH.is_file():
        return DEFAULT_REPORT_PATH
    if PUBLISHED_BRIEF_PATH.is_file():
        return PUBLISHED_BRIEF_PATH
    return None


def load_brief(path: Path | None = None) -> InvestmentBrief | None:
    target = resolve_brief_path(path)
    if target is None:
        return None
    raw = json.loads(target.read_text(encoding="utf-8"))
    brief = InvestmentBrief.model_validate(normalize_brief_dict(raw))
    return _normalize_loaded_brief(brief)


def _as_of_prefixed(ctx: str) -> bool:
    c = ctx.strip().lower()
    return c.startswith("as of") or ctx.strip().startswith("截至")


def _normalize_loaded_brief(brief: InvestmentBrief) -> InvestmentBrief:
    """Backfill date fields for older reports."""
    updates: dict = {}
    if not brief.report_date:
        updates["report_date"] = format_date_iso(analysis_date())
    if not _as_of_prefixed(brief.as_of_context):
        as_of = analysis_date()
        if brief.report_date:
            from datetime import date as date_cls

            try:
                as_of = date_cls.fromisoformat(brief.report_date)
            except ValueError:
                pass
        updates["as_of_context"] = build_as_of_context(brief.as_of_context, as_of=as_of)
    if not updates:
        return brief
    return brief.model_copy(update=updates)
